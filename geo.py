"""
지도 데이터 준비 — 최초 1회 실행: python geo.py
1) 행정동 경계(vuski/admdongkor 2026.07판)에서 인천 서해구·검단구만 골라 data/seohae.geojson 저장
2) 사업장 37개소 주소 → 좌표 변환(OpenStreetMap Nominatim) → data/site_coords.json 저장
   주소로 못 찾으면 시설명으로, 그래도 없으면 행정동 중심점(근사값)으로 대체
   좌표가 틀린 곳은 site_coords.json에서 lat·lng를 직접 고치고 approx를 false로 바꾸면 됨
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import config

DATA = Path.cwd() / 'data'
GEO_URL = ('https://raw.githubusercontent.com/vuski/admdongkor/master/'
           'ver20260701/HangJeongDong_ver20260701.geojson')
GEO_FILE = DATA / 'seohae.geojson'
COORD_FILE = DATA / 'site_coords.json'
GU_NAMES = ('서해구', '검단구')
HEADERS = {'User-Agent': 'SG-dashboard-demo/1.0 (youth project)'}


# ── 화면2에서 쓰는 함수 ──
def load():
    """(geojson, coords) 또는 파일이 없으면 None"""
    if not (GEO_FILE.exists() and COORD_FILE.exists()):
        return None
    gj = json.loads(GEO_FILE.read_text(encoding='utf-8'))
    coords = json.loads(COORD_FILE.read_text(encoding='utf-8'))
    return gj, coords


def _points(feat):
    g = feat['geometry']
    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
    return [p for poly in polys for p in poly[0]]


def bounds(gj):
    """[[최소 위도, 최소 경도], [최대 위도, 최대 경도]]"""
    pts = [p for f in gj['features'] for p in _points(f)]
    return [[min(p[1] for p in pts), min(p[0] for p in pts)],
            [max(p[1] for p in pts), max(p[0] for p in pts)]]


# ── 준비 작업 ──
def _fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def make_geojson():
    print('행정동 경계 내려받는 중 (약 35MB, 1~2분)...')
    data = json.loads(_fetch(GEO_URL))
    feats = [f for f in data['features']
             if f['properties']['sidonm'] == '인천광역시' and f['properties']['sggnm'] in GU_NAMES]
    gj = {'type': 'FeatureCollection', 'features': feats}
    DATA.mkdir(exist_ok=True)
    GEO_FILE.write_text(json.dumps(gj, ensure_ascii=False), encoding='utf-8')
    print(f'저장 완료: {GEO_FILE} (행정동 {len(feats)}개)')
    return gj


def _nominatim(q):
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
        {'q': q, 'format': 'json', 'limit': 1, 'countrycodes': 'kr'})
    try:
        res = json.loads(_fetch(url))
    except Exception as e:
        print('   검색 오류:', e)
        res = []
    time.sleep(1.1)   # Nominatim 이용 규칙: 1초에 1건
    return (float(res[0]['lat']), float(res[0]['lon'])) if res else None


def _inside(pt, bb):
    (lat0, lng0), (lat1, lng1) = bb
    return lat0 - 0.01 <= pt[0] <= lat1 + 0.01 and lng0 - 0.01 <= pt[1] <= lng1 + 0.01


def _center(feats):
    pts = [p for f in feats for p in _points(f)]
    return (sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts))


def _dong_center(addr, gj, gu='서해구'):
    """주소의 동 이름(예: '(검암동)' → '검암')과 맞는 행정동 중심점. 없으면 서해구 중심"""
    if '(' in addr:
        dong = addr.split('(')[-1].rstrip(')')
    else:
        dong = next((w for w in addr.split() if w.endswith('동')), '')
    key = dong.replace('동', '')[:2]
    hits = [f for f in gj['features'] if key and key in f['properties']['adm_nm']]
    if hits:
        return _center(hits[:1])
    return _center([f for f in gj['features'] if f['properties']['sggnm'] == gu])


def geocode_sites(gj):
    bb = bounds(gj)
    old = json.loads(COORD_FILE.read_text(encoding='utf-8')) if COORD_FILE.exists() else {}
    out = {}
    for s in config.SITES:
        prev = old.get(s['id'])
        if prev and not prev.get('approx'):
            out[s['id']] = prev            # 이미 찾았거나 직접 고친 좌표는 유지
            continue
        addr = s['addr'].split(' (')[0].split(',')[0]     # '(동)', ', 5층' 등 상세 표기 제외
        hit, src = None, ''
        if s['addr'] != config.ADDR_TBD:
            for gu in (s['gu'], '서구'):   # 서해구로 먼저 검색, 못 찾으면 개편 전 '서구'로 재검색
                hit = _nominatim(f'인천광역시 {gu} {addr}')
                if hit and _inside(hit, bb):
                    src = '주소'
                    break
                hit = None
        if not hit:
            hit = _nominatim(f"인천 {s['name']}")
            if hit and _inside(hit, bb):
                src = '시설명'
            else:
                hit = None
        if not hit:
            hit, src = _dong_center(s['addr'], gj, s['gu']), '행정동 중심(근사)'
        out[s['id']] = {'lat': round(hit[0], 6), 'lng': round(hit[1], 6),
                        'approx': src == '행정동 중심(근사)', 'source': src}
        print(f"{s['id']} {s['name']}: {src}")
    COORD_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    n_approx = sum(1 for v in out.values() if v['approx'])
    print(f'저장 완료: {COORD_FILE} (근사값 {n_approx}곳)')


if __name__ == '__main__':
    geojson = load()[0] if GEO_FILE.exists() and COORD_FILE.exists() else None
    if GEO_FILE.exists():
        geojson = json.loads(GEO_FILE.read_text(encoding='utf-8'))
        print(f'경계 파일 있음: {GEO_FILE}')
    else:
        geojson = make_geojson()
    geocode_sites(geojson)