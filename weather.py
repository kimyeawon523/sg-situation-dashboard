"""기상·대기질 정보 (공공데이터포털)
- 기상청 단기예보 조회서비스 · 초단기실황(getUltraSrtNcst): 매시 정각 자료, 40분 이후 제공
- 기상청 단기예보 조회서비스 · 초단기예보(getUltraSrtFcst): 매시 30분 발표, 45분 이후 제공, 6시간
- 기상청 기상특보 조회서비스 · 특보현황(getPwnStatus)
- 에어코리아 대기오염정보 · 시도별 실시간 측정정보(getCtprvnRltmMesureDnsty): 1시간 단위
서버 전체에서 1번만 받아 와 메모리에 최신값만 보관. 인증키가 없거나 일부가 실패하면 그 부분만 시연값 사용.
"""
import asyncio
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from nicegui import run

import config

NCST_URL = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst'
FCST_URL = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst'
WRN_URL = 'https://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus'
AIR_URL = 'https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty'
PTY_NAME = {0: '강수 없음', 1: '비', 2: '비/눈', 3: '눈', 5: '빗방울', 6: '빗방울·눈날림', 7: '눈날림'}
SKY_NAME = {1: '맑음', 3: '구름많음', 4: '흐림'}
GRADE_NAME = {1: '좋음', 2: '보통', 3: '나쁨', 4: '매우나쁨'}

data = {'weather': [], 'forecast': [], 'warnings': [], 'air': [],
        'updated': None, 'demo': True, 'error': ''}
_printed = {'stations': False}


def dfs_xy(lat, lng):
    """위경도 → 기상청 격자(nx, ny). 기상청 공개 변환식(LCC)"""
    RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    D = math.pi / 180.0
    re = RE / GRID
    s1, s2, olon, olat = SLAT1 * D, SLAT2 * D, OLON * D, OLAT * D
    sn = math.log(math.cos(s1) / math.cos(s2)) / \
        math.log(math.tan(math.pi / 4 + s2 / 2) / math.tan(math.pi / 4 + s1 / 2))
    sf = math.tan(math.pi / 4 + s1 / 2) ** sn * math.cos(s1) / sn
    ro = re * sf / math.tan(math.pi / 4 + olat / 2) ** sn
    ra = re * sf / math.tan(math.pi / 4 + lat * D / 2) ** sn
    th = lng * D - olon
    if th > math.pi:
        th -= 2 * math.pi
    if th < -math.pi:
        th += 2 * math.pi
    th *= sn
    return math.floor(ra * math.sin(th) + XO + 0.5), math.floor(ro - ra * math.cos(th) + YO + 0.5)


def _get(url, params):
    full = f'{url}?{urllib.parse.urlencode(params)}'
    with urllib.request.urlopen(full, timeout=15) as r:
        body = r.read().decode('utf-8')
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(body[:120])      # 인증키 오류 등은 XML로 응답됨


def _kma_items(res):
    """기상청 응답에서 item 목록 (자료 없음이면 빈 목록)"""
    body = res.get('response', {}).get('body') or {}
    items = body.get('items') or {}
    return items.get('item', []) if isinstance(items, dict) else []


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _key():
    return {'serviceKey': config.DATA_GO_KR_KEY, 'pageNo': 1, 'dataType': 'JSON'}


def _fetch_weather(p):
    base = datetime.now() - timedelta(minutes=40)
    nx, ny = dfs_xy(p['lat'], p['lng'])
    items = _kma_items(_get(NCST_URL, {**_key(), 'numOfRows': 20, 'base_date': base.strftime('%Y%m%d'),
                                       'base_time': base.strftime('%H00'), 'nx': nx, 'ny': ny}))
    v = {i['category']: i['obsrValue'] for i in items}
    return {'name': p['name'], 'temp': _num(v.get('T1H')) or 0.0, 'hum': _num(v.get('REH')) or 0.0,
            'wind': _num(v.get('WSD')) or 0.0, 'rain': _num(v.get('RN1')) or 0.0,
            'pty': int(_num(v.get('PTY')) or 0), 'time': base.strftime('%H:00')}


def _fetch_forecast(p):
    base = datetime.now() - timedelta(minutes=45)
    nx, ny = dfs_xy(p['lat'], p['lng'])
    items = _kma_items(_get(FCST_URL, {**_key(), 'numOfRows': 60, 'base_date': base.strftime('%Y%m%d'),
                                       'base_time': base.strftime('%H30'), 'nx': nx, 'ny': ny}))
    by = {}
    for i in items:
        by.setdefault(i['fcstDate'] + i['fcstTime'], {})[i['category']] = i['fcstValue']
    out = []
    for k in sorted(by)[:6]:
        v = by[k]
        out.append({'time': f'{k[8:10]}시', 'temp': _num(v.get('T1H')), 'sky': int(_num(v.get('SKY')) or 1),
                    'pty': int(_num(v.get('PTY')) or 0), 'rain': v.get('RN1', '강수없음')})
    return out


def _fetch_warnings():
    """특보현황 문장(t6)에서 인천이 포함된 특보만 추출. 예: 'o 강풍주의보 : 인천(인천서부, ...)'"""
    items = _kma_items(_get(WRN_URL, {**_key(), 'numOfRows': 10}))
    text = items[0].get('t6', '') if items else ''
    out = []
    for line in text.replace('\r', '').split('\n'):
        line = line.strip().lstrip('o').strip()
        if ':' not in line:
            continue
        kind, regions = line.split(':', 1)
        if config.WARN_REGION in regions:
            out.append({'kind': kind.strip(), 'regions': regions.strip()[:80]})
    return out


def _fetch_air():
    res = _get(AIR_URL, {'serviceKey': config.DATA_GO_KR_KEY, 'returnType': 'json', 'numOfRows': 100,
                         'pageNo': 1, 'sidoName': config.AIR_SIDO, 'ver': '1.0'})
    rows = [{'station': i.get('stationName'), 'time': (i.get('dataTime') or '')[-5:],
             'pm10': _num(i.get('pm10Value')), 'pm25': _num(i.get('pm25Value')), 'o3': _num(i.get('o3Value')),
             'pm10_grade': int(_num(i.get('pm10Grade')) or 0), 'pm25_grade': int(_num(i.get('pm25Grade')) or 0)}
            for i in res['response']['body']['items']]
    if not _printed['stations']:
        print(f"[대기질] {config.AIR_SIDO} 측정소:", ', '.join(r['station'] for r in rows))
        _printed['stations'] = True
    picked = [r for r in rows if r['station'] in config.AIR_STATIONS]
    return picked or rows[:6]


def _demo():
    now = datetime.now()
    hm = now.strftime('%H:00')
    hours = [(now + timedelta(hours=i)).strftime('%H시') for i in range(1, 7)]
    return {
        'weather': [
            {'name': '서해구', 'temp': 21.4, 'hum': 58, 'wind': 2.3, 'rain': 0.0, 'pty': 0, 'time': hm},
            {'name': '검단구', 'temp': 20.9, 'hum': 61, 'wind': 3.1, 'rain': 0.0, 'pty': 0, 'time': hm}],
        'forecast': [
            {'time': hours[0], 'temp': 21, 'sky': 1, 'pty': 0, 'rain': '강수없음'},
            {'time': hours[1], 'temp': 20, 'sky': 3, 'pty': 0, 'rain': '강수없음'},
            {'time': hours[2], 'temp': 19, 'sky': 4, 'pty': 1, 'rain': '1.0mm'},
            {'time': hours[3], 'temp': 19, 'sky': 4, 'pty': 1, 'rain': '3.0mm'},
            {'time': hours[4], 'temp': 18, 'sky': 3, 'pty': 0, 'rain': '강수없음'},
            {'time': hours[5], 'temp': 18, 'sky': 1, 'pty': 0, 'rain': '강수없음'}],
        'warnings': [{'kind': '강풍주의보', 'regions': '인천(인천서부, 인천동부)'}],
        'air': [
            {'station': '연희', 'time': hm, 'pm10': 38, 'pm25': 19, 'o3': 0.031, 'pm10_grade': 2, 'pm25_grade': 2},
            {'station': '석남', 'time': hm, 'pm10': 92, 'pm25': 41, 'o3': 0.028, 'pm10_grade': 3, 'pm25_grade': 3},
            {'station': '청라', 'time': hm, 'pm10': 25, 'pm25': 12, 'o3': 0.035, 'pm10_grade': 1, 'pm25_grade': 1},
            {'station': '검단', 'time': hm, 'pm10': 44, 'pm25': 22, 'o3': 0.030, 'pm10_grade': 2, 'pm25_grade': 2}]}


def refresh():
    """최신값 받아 오기. 실패한 항목만 시연값으로 채우고 오류 기록"""
    demo = _demo()
    if not config.DATA_GO_KR_KEY:
        data.update(demo, demo=True, error='인증키 미설정', updated=time.time())
        return
    new, errs = {}, []
    jobs = [('weather', '날씨', lambda: [_fetch_weather(p) for p in config.WEATHER_POINTS]),
            ('forecast', '예보', lambda: _fetch_forecast(config.WEATHER_POINTS[0])),
            ('warnings', '특보', _fetch_warnings),
            ('air', '대기질', _fetch_air)]
    for key, label, job in jobs:
        try:
            new[key] = job()
        except Exception as e:
            print(f'[기상·대기질 오류] {label}:', e)
            errs.append(label)
            new[key] = demo[key]
    data.update(new, demo=bool(errs), error=('일부 시연값: ' + ', '.join(errs)) if errs else '',
                updated=time.time())


def conditions():
    """영향 사업장 판단 조건 {조건: 근거}"""
    c = {}
    kinds = [w['kind'] for w in data['warnings']]
    rain_now = [w['name'] for w in data['weather'] if w['pty']]
    rain_soon = [f['time'] for f in data['forecast'] if f['pty']]
    if any(k.startswith(('호우', '대설')) for k in kinds):
        c['강수'] = '기상특보 발효'
    elif rain_now:
        c['강수'] = f"{', '.join(rain_now)} 현재 강수"
    elif rain_soon:
        c['강수'] = f'{rain_soon[0]}부터 강수 예보'
    hot = [w['name'] for w in data['weather'] if w['temp'] >= config.HEAT_TEMP]
    if any(k.startswith('폭염') for k in kinds) or hot:
        c['폭염'] = '폭염특보 발효' if any(k.startswith('폭염') for k in kinds) else f'기온 {config.HEAT_TEMP}℃ 이상'
    bad = [a['station'] for a in data['air'] if max(a['pm10_grade'], a['pm25_grade']) >= 3]
    if bad:
        c['미세먼지'] = f"{', '.join(bad)} 측정소 나쁨 이상"
    windy = [w['name'] for w in data['weather'] if w['wind'] >= config.WIND_MS]
    if any(k.startswith('강풍') for k in kinds) or windy:
        c['강풍'] = '강풍특보 발효' if any(k.startswith('강풍') for k in kinds) else f'풍속 {config.WIND_MS}m/s 이상'
    return c


def alerts():
    """현재 환경 경보 [(수준, 내용)] — 특보 + 기준 초과 (기준은 config [가안])"""
    out = []
    for w in data['warnings']:
        out.append(('경고' if w['kind'].endswith('경보') else '주의', f"기상특보 · {w['kind']}"))
    for w in data['weather']:
        if w['temp'] >= config.HEAT_TEMP:
            out.append(('주의', f"{w['name']} 기온 {w['temp']:.1f}℃ · 폭염 대비"))
        if w['wind'] >= config.WIND_MS:
            out.append(('주의', f"{w['name']} 풍속 {w['wind']:.1f}m/s · 강풍"))
        if w['pty']:
            out.append(('알림', f"{w['name']} {PTY_NAME.get(w['pty'], '강수')} · 1시간 {w['rain']:.1f}mm"))
    for a in data['air']:
        g = max(a['pm10_grade'], a['pm25_grade'])
        if g >= 3:
            out.append(('주의', f"{a['station']} 측정소 미세먼지 {GRADE_NAME[g]}"))
    return out


async def _loop():
    while True:
        await run.io_bound(refresh)
        await asyncio.sleep(config.WEATHER_REFRESH_MIN * 60)


def start():
    """main.py에서 서버 시작 시 1번 호출"""
    asyncio.create_task(_loop())