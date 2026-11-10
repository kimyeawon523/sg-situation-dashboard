"""국가교통정보센터(ITS) 공개 CCTV — 서해구·검단구 주변 도로 CCTV 실시간 영상 주소
영상 주소는 일정 시간 뒤 만료되므로 ITS_REFRESH_MIN마다 다시 받아 옴.
키 파일(its_key.txt)이 없거나 오류면 빈 목록 → 화면5·6은 녹화 영상으로 대체."""
import asyncio
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from nicegui import run

import config
import geo

from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import Response
from nicegui import app

URL = 'https://openapi.its.go.kr:9443/cctvInfo'
KEY_FILE = config.BASE / 'its_key.txt'
data = {'cams': [], 'updated': None, 'error': ''}

CACHE_FILE = config.BASE / 'data' / 'its_cache.json'   # 재시작 시 호출 절약용


def _load_cache():
    """최근 ITS_REFRESH_MIN분 안에 받은 목록이 있으면 사용 (서버 재시작 시 호출 안 함)"""
    if not CACHE_FILE.exists():
        return False
    try:
        c = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return False
    if time.time() - c.get('updated', 0) > config.ITS_REFRESH_MIN * 60 or not c.get('cams'):
        return False
    data.update(cams=c['cams'], error='', updated=c['updated'])
    print(f"[ITS CCTV] 저장된 목록 사용 {len(c['cams'])}대 (호출 없음)")
    return True


def _save_cache():
    CACHE_FILE.write_text(json.dumps({'cams': data['cams'], 'updated': data['updated']},
                                     ensure_ascii=False), encoding='utf-8')

def _key():
    if not KEY_FILE.exists():
        return ''
    return KEY_FILE.read_text(encoding='utf-8-sig').strip().strip('\'"').strip()


def _bbox():
    """(최소 경도, 최대 경도, 최소 위도, 최대 위도)"""
    d = geo.load()
    if d:
        (la0, lo0), (la1, lo1) = geo.bounds(d[0])
    else:
        la0, lo0, la1, lo1 = 37.48, 126.55, 37.65, 126.75
    m = config.ITS_MARGIN
    return lo0 - m, lo1 + m, la0 - m, la1 + m


def _fetch(kind, box):
    q = {'apiKey': _key(), 'type': kind, 'cctvType': 1, 'minX': box[0], 'maxX': box[1],
         'minY': box[2], 'maxY': box[3], 'getType': 'json'}
    req = urllib.request.Request(f'{URL}?{urllib.parse.urlencode(q)}', headers={
        'Referer': config.ITS_SITE,          # 인증키 신청 시 등록한 사용처
        'Origin': config.ITS_SITE,
        'User-Agent': 'Mozilla/5.0',
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode('utf-8')
    try:
        res = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(body[:120])
    rows = res.get('response', {}).get('data', [])
    if isinstance(rows, dict):
        rows = [rows]
    return [{'name': (x.get('cctvname') or '').strip(), 'url': x.get('cctvurl'),
             'kind': '고속도로' if kind == 'ex' else '국도'}
            for x in rows if x.get('cctvurl')]


def refresh():
    if not _key():
        data.update(cams=[], error='its_key.txt 없음', updated=time.time())
        return
    box, cams, errs = _bbox(), [], []
    for kind in config.ITS_TYPES:
        try:
            cams += _fetch(kind, box)
        except Exception as e:
            print(f'[ITS CCTV 오류] {kind}:', e)
            errs.append(f'{kind}: {str(e)[:60]}')
    if not cams and data['cams']:
        # 이번 요청이 모두 실패하면 직전 목록 유지 (영상 주소가 아직 유효할 수 있음)
        data.update(error='갱신 실패, 직전 목록 사용 · ' + ' / '.join(errs))
        print('[ITS CCTV] 갱신 실패, 직전 목록 유지')
        return
    seen, uniq = set(), []
    for c in cams:
        if c['name'] not in seen:
            seen.add(c['name'])
            uniq.append(c)
    data.update(cams=uniq, error=' / '.join(errs), updated=time.time())
    print(f'[ITS CCTV] 서해구·검단구 주변 {len(uniq)}대 (호출 {len(config.ITS_TYPES)}건)')
    if uniq:
        _save_cache()


async def _loop():
    if _load_cache():        # 재시작 직후: 저장된 목록이 유효하면 호출 생략
        await asyncio.sleep(config.ITS_REFRESH_MIN * 60)
    while True:
        await run.io_bound(refresh)
        await asyncio.sleep(config.ITS_REFRESH_MIN * 60)


def start():
    """main.py에서 서버 시작 시 1번 호출"""
    asyncio.create_task(_loop())


# ── 영상 중계: 브라우저 대신 서버가 CCTV 영상을 받아 전달 (영상 서버의 브라우저 직접 재생 제한 회피) ──

_client = {'c': None}
_allowed = set()    # ITS가 알려 준 영상 서버만 중계


def _hosts():
    return {urlparse(c['url']).hostname for c in data['cams']} | _allowed


@app.get('/hls')
async def hls_proxy(u: str):
    if urlparse(u).hostname not in _hosts():
        return Response('허용되지 않은 주소', status_code=403)
    if _client['c'] is None:
        _client['c'] = httpx.AsyncClient(timeout=10, follow_redirects=True,
                                         headers={'User-Agent': 'Mozilla/5.0'})
    try:
        r = await _client['c'].get(u)
    except Exception as e:
        return Response(str(e)[:100], status_code=502)
    ctype = r.headers.get('content-type', '')
    if '.m3u8' in u.split('?')[0] or 'mpegurl' in ctype.lower():
        base = str(r.url)
        _allowed.add(urlparse(base).hostname)
        lines = []
        for line in r.text.splitlines():
            s = line.strip()
            if s and not s.startswith('#'):          # 영상 조각 주소도 중계 주소로 바꿈
                line = '/hls?u=' + quote(urljoin(base, s), safe='')
            lines.append(line)
        return Response('\n'.join(lines), media_type='application/vnd.apple.mpegurl')
    return Response(r.content, status_code=r.status_code, media_type=ctype or 'video/mp2t')