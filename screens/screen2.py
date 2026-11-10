"""화면2 · 지도 / 기상·환경 (v4, 제목 옆 탭으로 전환)
[사업장 지도] 밝은 회색 지도 + 서해구·검단구 경계 + 사업장 상태 마커, 지도 위 상태 칩(필터), 오른쪽 끝 검색 패널
[기상·환경]   현재 날씨 · 지표 타일 · 측정소별 대기질 · 시간별 예보 · 영향 사업장
화면1에서 상황을 고르면 지도로 전환 후 해당 사업장 확대."""
import math
import re

from nicegui import ui

import config
import geo
import state as S
import weather
from screens import screen_root, header, live, clock, T, C, B

STATUS_ORDER = ['미조치', '이상', '확인 필요', '정상', '확인 불가']
TABS = ['전체'] + STATUS_ORDER
GU_STYLE = {
    '서해구': {'color': '#2783C5', 'weight': 2, 'fillColor': '#18AAD5', 'fillOpacity': 0.10},
    '검단구': {'color': '#6E8A0A', 'weight': 2, 'fillColor': '#A1BE16', 'fillOpacity': 0.10},
}
GU_SWATCH = {'서해구': 'background:rgba(24,170,213,.18);border:2px solid #2783C5',
             '검단구': 'background:rgba(161,190,22,.18);border:2px solid #6E8A0A'}
# 사업장 주소의 동 → 가까운 대기질 측정소. 없거나 측정값이 없으면 구 기본값(검단구 = 검단, 서해구 = 연희)
DONG_STATION = {'청라': '청라', '석남': '석남', '가좌': '석남', '가정': '석남', '원창': '석남', '신현': '석남',
                '심곡': '연희', '연희': '연희', '공촌': '연희', '검암': '연희',
                '마전': '검단', '왕길': '검단', '당하': '검단', '오류': '검단', '원당': '원당', '불로': '원당'}
STATION_ORDER = ['연희', '검단', '석남', '청라', '원당']   # 사업장별 대기질 표시 순서 (고정)
TIP_OPTIONS = {'direction': 'top', 'offset': [0, -4], 'className': 's2-tip', 'opacity': 1}
PIN_PATH = 'M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20C24 5.4 18.6 0 12 0z'
LEVEL_COLOR = {'경고': C['alarm'], '주의': C['warn'], '이상': C['warn'], '알림': C['pending']}
GRADE_COLOR = {1: C['info'], 2: C['ok'], 3: C['warn'], 4: C['alarm']}   # 대기질 좋음·보통·나쁨·매우나쁨
SKY_EMOJI = {1: '☀️', 3: '⛅', 4: '☁️'}
PTY_EMOJI = {1: '🌧️', 2: '🌨️', 3: '❄️', 5: '🌦️', 6: '🌨️', 7: '🌨️'}


def sky_emoji(sky, pty):
    """강수가 있으면 강수 아이콘, 없으면 하늘 상태 아이콘"""
    return PTY_EMOJI.get(pty, '🌧️') if pty else SKY_EMOJI.get(sky, '☀️')


def sky_name(sky, pty):
    return weather.PTY_NAME.get(pty, '강수') if pty else weather.SKY_NAME.get(sky, '맑음')


CSS = f"""
<style>
/* 제목 옆 페이지 탭 */
.s2-ptabs {{ display:inline-flex; gap:4px; padding:5px; margin-left:12px; border-radius:999px; background:#ECEFF3; }}
.s2-ptab {{ display:flex; align-items:center; gap:8px; padding:8px 22px; border-radius:999px; font-size:21px;
           font-weight:600; color:{T['muted']}; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s2-ptab .q-icon {{ font-size:24px; }}
.s2-ptab.on {{ background:{T['panel']}; color:{B['blue']}; box-shadow:0 2px 8px rgba(16,24,40,.08); }}
.s2-ptab-dot {{ width:10px; height:10px; border-radius:50%; background:{C['alarm']}; }}

/* 지도 */
.s2-wrap {{ flex:1; position:relative; min-height:0; }}
.s2-unzoom {{ position:absolute; inset:0; zoom:var(--sg-unzoom, 1); }}
.s2-map .leaflet-tile-pane {{ filter:grayscale(.65) brightness(1.04); }}
.s2-map.picking, .s2-map.picking .leaflet-interactive {{ cursor:crosshair !important; }}

/* 마커: 재난·긴급 미조치 = 큰 마커 + 바닥 고리, 2건 이상 = 숫자 배지 */
.s2-pin {{ background:none; border:none; }}
.s2-pinbox {{ position:relative; width:100%; height:100%; }}
.s2-pinbox svg {{ position:relative; z-index:1; display:block; filter:drop-shadow(0 3px 4px rgba(15,23,42,.30)); }}
.s2-pin-big svg {{ animation:s2-bounce 1.4s ease-in-out infinite; }}
@keyframes s2-bounce {{ 0%,100% {{ transform:translateY(0); }} 50% {{ transform:translateY(-6px); }} }}
.s2-ring {{ position:absolute; left:50%; bottom:-6px; width:26px; height:12px; margin-left:-13px;
           border:3px solid; border-radius:50%; animation:s2-ring 1.6s ease-out infinite; }}
@keyframes s2-ring {{ 0% {{ transform:scale(.6); opacity:.9; }} 100% {{ transform:scale(2.8); opacity:0; }} }}
.s2-badge {{ position:absolute; top:-6px; right:-10px; z-index:2; min-width:22px; height:22px; padding:0 6px;
            border-radius:999px; background:#1A1F27; color:#fff; border:2px solid #fff;
            font:700 13px/18px 'Pretendard Variable', Pretendard, sans-serif; text-align:center; }}

/* 마우스 올림 정보창 */
.leaflet-tooltip.s2-tip {{ font-family:'Pretendard Variable', Pretendard, 'Malgun Gothic', sans-serif;
          font-size:15px; line-height:1.6; padding:12px 16px; border:none; border-radius:16px;
          box-shadow:0 10px 30px rgba(15,23,42,.18); }}
.s2-tip-name {{ font-size:19px; font-weight:700; }}
.s2-tip-addr {{ color:{T['muted']}; margin-bottom:4px; }}
.s2-tip-inc {{ font-weight:600; }}
.s2-tip-note {{ color:{T['muted']}; font-size:13px; margin-top:4px; }}

/* 지도 위 요소 (80% 고정 크기) */
.s2-chipbar {{ position:absolute; left:70px; top:16px; z-index:1000; zoom:var(--sg-nav-zoom, 1);
              display:flex; gap:4px; padding:6px; border-radius:999px; background:rgba(255,255,255,.92);
              backdrop-filter:blur(8px); box-shadow:var(--sg-shadow); }}
.s2-fchip {{ display:flex; align-items:center; gap:8px; padding:8px 16px; border-radius:999px; font-size:17px;
            color:{T['muted']}; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s2-fchip:hover {{ background:var(--sg-soft); }}
.s2-fchip .d {{ width:10px; height:10px; border-radius:50%; background:var(--c); }}
.s2-fchip .n {{ font-weight:700; color:{T['text']}; font-variant-numeric:tabular-nums; }}
.s2-fchip.on {{ background:var(--c); color:#fff; }}
.s2-fchip.on .n {{ color:#fff; }}
.s2-fchip.on .d {{ background:#fff; }}
.s2-sep {{ width:1px; align-self:stretch; margin:6px 4px; background:#E3E7EC; }}
.s2-reset {{ color:{B['blue']}; font-weight:600; }}
.s2-reset:hover {{ background:{B['blue']}14; }}
.s2-reset .q-icon {{ font-size:20px; }}
.s2-legend {{ position:absolute; left:20px; bottom:24px; z-index:1000; zoom:var(--sg-nav-zoom, 1);
             padding:16px 20px; display:flex; flex-direction:column; gap:8px; font-size:15px;
             background:rgba(255,255,255,.92) !important; backdrop-filter:blur(8px); }}
.s2-legend .h {{ font-size:13px; color:{T['muted']}; margin-top:4px; }}
.s2-swatch {{ width:32px; height:18px; border-radius:6px; }}
.s2-focus {{ position:absolute; left:50%; top:84px; transform:translateX(-50%); z-index:1000;
            zoom:var(--sg-nav-zoom, 1); padding:10px 12px 10px 20px; display:flex; align-items:center; gap:12px;
            font-size:18px; border-radius:999px !important; }}
.s2-alert {{ position:absolute; right:70px; bottom:24px; z-index:1000; zoom:var(--sg-nav-zoom, 1);
            width:460px; padding:18px 20px; display:flex; flex-direction:column; gap:10px; font-size:16px;
            box-shadow:0 0 0 3px {C['warn']}33, var(--sg-shadow-up) !important; }}
.s2-alert-row {{ display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:14px; background:var(--sg-soft); }}
.s2-empty {{ padding:40px; font-size:26px; }}

/* 오른쪽 검색 패널 (80% 고정 크기) */
.s2-side-zone {{ position:fixed; right:0; top:0; width:10px; height:var(--sg-nav-h, 100vh); z-index:3000;
                zoom:var(--sg-nav-zoom, 1); }}
.s2-handle {{ position:fixed; right:0; top:40%; z-index:2999; zoom:var(--sg-nav-zoom, 1);
             display:flex; flex-direction:column; align-items:center; gap:8px; padding:18px 10px;
             background:linear-gradient(180deg, {B['sky']}, {B['blue']}); color:#fff; border-radius:16px 0 0 16px;
             font-size:16px; font-weight:600; writing-mode:vertical-rl;
             box-shadow:-4px 4px 16px rgba(39,131,197,.30); cursor:pointer; }}
.s2-side {{ position:fixed; right:0; top:0; width:440px; height:var(--sg-nav-h, 100vh); z-index:3001;
           zoom:var(--sg-nav-zoom, 1); display:flex; flex-direction:column; gap:14px; padding:26px 20px;
           background:{T['panel']}; border-radius:24px 0 0 24px; box-shadow:-10px 0 40px rgba(16,24,40,.14);
           transform:translateX(105%); transition:transform .3s var(--sg-ease) .15s; }}
.s2-side-zone:hover ~ .s2-side, .s2-handle:hover ~ .s2-side {{ transform:translateX(0); transition-delay:.4s; }}
.s2-side:hover, .s2-side:focus-within {{ transform:translateX(0); transition-delay:0s; }}
.s2-side-title {{ font-size:22px; font-weight:700; }}
.s2-filter {{ font-size:14px; color:{T['muted']}; }}
.s2-list {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:2px; }}
.s2-item {{ display:flex; align-items:center; gap:12px; padding:12px 12px; border-radius:14px; cursor:pointer;
           transition:background .2s var(--sg-ease); }}
.s2-item:hover {{ background:var(--sg-soft); }}
.s2-item.on {{ background:{B['blue']}12; }}
.s2-item-name {{ font-size:17px; font-weight:650; }}
.s2-item-sub {{ font-size:14px; color:{T['muted']}; }}
.s2-dot {{ width:14px; height:14px; border-radius:50%; flex-shrink:0;
          box-shadow:0 0 0 3px color-mix(in srgb, currentColor 0%, #fff), 0 0 0 4px rgba(0,0,0,.06); }}
.s2-card {{ border-radius:18px; padding:16px 18px; background:var(--sg-soft);
           display:flex; flex-direction:column; gap:8px; font-size:16px; }}
.s2-card-sub {{ font-size:15px; font-weight:650; margin-top:4px; }}
.s2-near {{ display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:12px; cursor:pointer;
           background:{T['panel']}; }}
.s2-near:hover {{ box-shadow:var(--sg-shadow); }}

/* ===== 기상·환경 페이지 ===== */
.s2-envwrap {{ flex:1; min-height:0; padding:22px 28px; display:flex; flex-direction:column; gap:18px; overflow:auto;
              background:linear-gradient(180deg, #E6F4FA 0%, {T['bg']} 42%); }}
.s2-h1 {{ font-size:30px; font-weight:700; letter-spacing:-0.02em; }}
.s2-demo {{ padding:4px 14px; border-radius:999px; background:#FFF4D6; color:#8A6400; font-size:16px; font-weight:600; }}
.s2-band {{ display:flex; align-items:center; flex-wrap:wrap; gap:12px; padding:14px 24px; border-radius:20px;
           font-size:20px; flex-shrink:0; }}
.s2-band.calm {{ background:rgba(255,255,255,.8); color:{T['muted']}; box-shadow:var(--sg-shadow); }}
.s2-band.on {{ color:#fff; font-weight:600; }}
.s2-band.alert {{ background:#FDECEC; color:#D62F32; font-weight:700;
                 box-shadow:inset 0 0 0 2px #E5383B55, 0 8px 24px rgba(229,56,59,.15); }}
.s2-band.alert b {{ font-weight:800; }}
.s2-band .q-icon {{ font-size:28px; }}
.s2-achip {{ padding:5px 14px; border-radius:999px; font-size:16px; font-weight:600; white-space:nowrap;
            color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fff); }}
.s2-env-grid {{ display:grid; grid-template-columns:minmax(0,1.55fr) minmax(0,1fr); gap:20px;
               grid-template-areas:"hero hour" "tiles impact" "air air"; }}
.s2-env-grid > div {{ min-width:0; display:flex; flex-direction:column; }}
.s2-env-grid > div > * {{ flex:1; }}
.s2-emo {{ font-family:'Segoe UI Emoji','Apple Color Emoji','Noto Color Emoji',sans-serif; line-height:1; }}
.s2-cap {{ font-size:18px; color:{T['muted']}; }}

/* 현재 날씨 */
.s2-hero {{ padding:28px 34px; display:flex; flex-direction:column; gap:16px;
           background:linear-gradient(135deg, #FFFFFF 0%, #F1FAFD 100%) !important; }}
.s2-temp {{ font-size:120px; font-weight:300; letter-spacing:-0.04em; line-height:1; font-variant-numeric:tabular-nums; }}
.s2-temp sup {{ font-size:40px; font-weight:400; vertical-align:top; position:relative; top:14px; margin-left:4px; }}
.s2-halves {{ display:grid; grid-template-columns:1fr 1fr; }}
.s2-half {{ display:flex; flex-direction:column; gap:12px; padding:4px 32px; min-width:0; }}
.s2-half:first-child {{ padding-left:4px; }}
.s2-half + .s2-half {{ border-left:1px solid #E3EAF0; }}
.s2-hname {{ font-size:26px; font-weight:700; }}
.s2-half .s2-temp {{ font-size:100px; }}
           box-shadow:0 1px 3px rgba(16,24,40,.06); display:flex; flex-direction:column; gap:6px; }}
.s2-summary {{ display:flex; align-items:center; gap:18px; padding:20px 26px; border-radius:20px; font-size:26px;
              background:color-mix(in srgb, var(--c) 10%, #fff);
              box-shadow:inset 0 0 0 2px color-mix(in srgb, var(--c) 22%, transparent); }}
.s2-summary b {{ color:var(--c); font-weight:700; }}

/* 지표 타일 */
.s2-tiles {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
.s2-tile {{ padding:20px 22px; border-radius:22px; background:{T['panel']}; box-shadow:var(--sg-shadow);
           display:flex; flex-direction:column; gap:6px; transition:transform .25s var(--sg-ease), box-shadow .25s; }}
.s2-tile:hover {{ transform:translateY(-2px); box-shadow:var(--sg-shadow-up); }}
.s2-tile-top {{ display:flex; align-items:center; gap:12px; font-size:22px; font-weight:600; color:{T['text']}; }}
.s2-tile-top .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:44px; height:44px;
                       border-radius:14px; font-size:24px; color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fff); }}
.s2-tile-v {{ font-size:40px; font-weight:700; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; margin-top:2px; }}
.s2-tile-s {{ font-size:17px; color:{T['muted']}; }}

/* 공통 상자 */
.s2-box {{ padding:24px 28px; display:flex; flex-direction:column; gap:12px; }}
.s2-box-title {{ display:flex; align-items:center; gap:10px; font-size:22px; font-weight:650; margin-bottom:4px; }}
.s2-box-title .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:40px; height:40px;
                        border-radius:12px; font-size:22px; color:{B['blue']}; background:{B['blue']}12; }}
.s2-box-title .r {{ margin-left:auto; font-size:15px; font-weight:400; color:{T['muted']}; }}

/* 대기질 반원 게이지: 평소 옅게, 나쁨 이상만 진하게 */
.s2-gauges {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:16px; }}
.s2-gauge {{ padding:18px 18px 16px; border-radius:20px; background:var(--sg-soft);
            display:flex; flex-direction:column; gap:8px; transition:all .3s var(--sg-ease); }}
.s2-gauge.bad {{ background:color-mix(in srgb, var(--c) 8%, #fff);
                box-shadow:inset 0 0 0 2px color-mix(in srgb, var(--c) 45%, transparent); }}
.s2-gauge-t {{ font-size:23px; font-weight:700; }}
.s2-gauge.bad .s2-gauge-t {{ color:var(--c); }}
.s2-gauge svg {{ display:block; width:100%; max-width:380px; height:auto; margin:0 auto; }}
.s2-gvals {{ display:flex; justify-content:center; align-items:center; gap:10px; font-size:17px; color:{T['muted']}; }}
.s2-gvals b {{ color:{T['text']}; font-weight:700; font-variant-numeric:tabular-nums; }}
.s2-gchips {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:8px; }}
.s2-gchip {{ padding:10px 20px; border-radius:999px; background:#fff; font-size:21px; color:{T['text']}; cursor:pointer;
            box-shadow:0 1px 2px rgba(16,24,40,.08); transition:all .2s var(--sg-ease); }}
.s2-gauge.bad .s2-gchip {{ color:var(--c); font-weight:700; }}
.s2-gchip:hover {{ background:{B['blue']}; color:#fff !important; }}

/* 시간별 예보: 시간을 크고 굵게 */
.s2-hour {{ display:grid; grid-template-columns:100px 56px 1fr 110px 140px; align-items:center; gap:12px;
           padding:8px 18px; border-radius:16px; }}
.s2-hour.rain {{ background:{B['blue']}0F; }}
.s2-hour-t {{ font-size:26px; font-weight:700; color:{T['text']}; font-variant-numeric:tabular-nums; }}
.s2-hour.rain .s2-hour-t {{ color:{B['blue']}; }}
.s2-hour-n {{ font-size:20px; font-weight:600; }}
.s2-hour-temp {{ font-size:34px; letter-spacing:-0.02em; }}
.s2-hour-temp sup {{ font-size:16px; vertical-align:top; position:relative; top:4px; }}
.s2-hour-r {{ font-size:16px; color:{T['muted']}; text-align:right; }}
.s2-hour.rain .s2-hour-r {{ color:{B['blue']}; font-weight:650; }}

/* 영향 사업장 */
.s2-impact {{ padding:22px 24px; border-radius:20px; background:#FFF6E8; display:flex; flex-direction:column; gap:14px; }}
.s2-impact > .row > div:last-child {{ font-size:24px !important; }}
.s2-impact .s2-pill {{ font-size:19px !important; padding:4px 14px; }}
.s2-impact-act {{ font-size:22px; font-weight:650; color:#9A5A00; }}
.s2-chips {{ display:flex; flex-wrap:wrap; gap:10px; }}
.s2-sitechip {{ padding:10px 20px; border-radius:999px; background:#fff; font-size:21px; cursor:pointer;
               box-shadow:0 1px 3px rgba(16,24,40,.08); transition:all .2s var(--sg-ease); }}
.s2-sitechip:hover {{ background:{B['blue']}; color:#fff; }}
.s2-ok {{ display:flex; align-items:center; gap:10px; padding:16px 20px; border-radius:18px;
         background:#2EA04312; color:#1E7A34; font-size:19px; font-weight:600; }}
.s2-src {{ font-size:15px; color:{T['muted']}; }}
</style>
"""


def pin_icon(status, selected, high=False, count=0):
    """물방울 마커 (JS 식). 재난·긴급 미조치 = 큰 마커 + 바닥 고리, 미조치 2건 이상 = 숫자 배지, 선택 = 검은 테두리"""
    big = high and status == '미조치'
    w = 50 if selected else 46 if big else {'미조치': 36, '이상': 34}.get(status, 30)
    h = round(w * 4 / 3)
    color = S.STATUS_COLOR[status]
    stroke = '#1A1F27' if selected else '#FFFFFF'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="-1 -1 26 34">'
           f'<path d="{PIN_PATH}" fill="{color}" stroke="{stroke}" stroke-width="1.6"/>'
           f'<circle cx="12" cy="12" r="4.5" fill="#FFFFFF"/></svg>')
    ring = f'<span class="s2-ring" style="border-color:{color}"></span>' if big else ''
    badge = f'<span class="s2-badge">{count}</span>' if count >= 2 else ''
    html = f'<div class="s2-pinbox">{ring}{svg}{badge}</div>'
    cls = 's2-pin' + (' s2-pin-big' if big else '')
    return (f"L.divIcon({{html: '{html}', className: '{cls}', iconSize: [{w}, {h}], "
            f"iconAnchor: [{w // 2}, {h}], tooltipAnchor: [0, -{h}]}})")


def reason(site_id):
    """목록 한 줄 사유"""
    s = S.state.sites[site_id]
    st = S.site_status(site_id)
    if st == '미조치':
        incs = S.open_incidents(site_id)
        top = min(incs, key=lambda i: S.GRADE_RANK[i['grade']])
        return f"{top['grade']} · {top['type']}" + (f' 외 {len(incs) - 1}건' if len(incs) > 1 else '')
    if st == '이상':
        r = [f'{k} {v}' for k, v in s['equip'].items() if v != '정상']
        r += [s['aux']] if s['aux'] else []
        r += [f"이상 보고 · {s.get('report_note') or s['report']}"] if s['report'] != '정상' else []
        return ', '.join(r)
    if st in ('확인 불가', '확인 필요'):
        return S.unknown_reason(site_id)
    return f"{s['dept']} · {s['gu']}"


def tip_html(site_id, approx):
    s = S.state.sites[site_id]
    st = S.site_status(site_id)
    lines = [f'<div class="s2-tip-name">{s["name"]}</div>',
             f'<div class="s2-tip-addr">{config.full_addr(s)}</div>',
             f'<div>담당 부서 · {s["dept"]}</div>',
             f'<div>AI·경보 연계 · {"연계" if s["linked"] else "미연계"}</div>',
             f'<div>상태 · <b style="color:{S.STATUS_COLOR[st]}">{st}</b></div>']
    for inc in S.open_incidents(site_id):
        lines.append(f'<div class="s2-tip-inc" style="color:{S.GRADE_COLOR[inc["grade"]]}">'
                     f'· [{inc["grade"]}] {inc["type"]} ({inc["loc"]}) · {S.ago(inc["start"])} 경과</div>')
    if st == '이상':
        lines.append(f'<div class="s2-tip-inc" style="color:{C["warn"]}">· {reason(site_id)}</div>')
    if approx:
        lines.append('<div class="s2-tip-note">※ 위치는 행정동 중심 근사값</div>')
    return ''.join(lines)


def dist_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a['lat'], a['lng'], b['lat'], b['lng']])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def all_alerts():
    """환경 경보(날씨·대기질) + 사업장 보조 설비 이상 [(수준, 내용)]"""
    out = list(weather.alerts())
    out += [('이상', f"{s['name']} · {s['aux']}") for s in S.state.sites.values() if s.get('aux')]
    return out


def summary_text(d):
    """현재 날씨 요약 (아이콘, 강조색, HTML). 핵심어는 <b>로 강조"""
    fc, ws = d['forecast'], d['weather']
    now_rain = [w for w in ws if w['pty']]
    soon = next((f for f in fc if f['pty']), None)
    if now_rain:
        w = now_rain[0]
        head = f"<b>{w['name']} 지금 {weather.PTY_NAME.get(w['pty'], '강수')}</b> · 1시간 {w['rain']:.1f}mm"
        emo, col = sky_emoji(4, w['pty']), B['blue']
    elif soon:
        amount = '' if soon['rain'] in ('강수없음', None) else f" ({soon['rain']})"
        head = f"<b>{soon['time']}부터 {weather.PTY_NAME.get(soon['pty'], '강수')}</b> 예보{amount}"
        emo, col = sky_emoji(soon['sky'], soon['pty']), B['blue']
    else:
        head, emo, col = '<b>향후 6시간 강수 없음</b>', '🌤️', C['ok']
    parts = [head]
    temps = [f['temp'] for f in fc if f['temp'] is not None]
    if temps:
        parts.append(f'기온 <b>{min(temps):g}~{max(temps):g}℃</b>')
    windy = [w['name'] for w in ws if w['wind'] >= config.WIND_MS]
    if windy:
        parts.append(f"<b>{', '.join(windy)} 강풍 주의</b>")
        col = C['warn']
    return emo, col, ' · '.join(parts)


def gauge_svg(grade):
    """반원 게이지. 좋음·보통이면 옅게, 나쁨 이상이면 현재 칸과 가운데를 진하게"""
    cx, cy, r = 100, 100, 78
    bad = grade >= 3

    def pt(rad, deg):
        a = math.radians(deg)
        return cx + rad * math.cos(a), cy - rad * math.sin(a)

    parts = []
    for g in (1, 2, 3, 4):
        on = g == grade
        op = 1 if (on and bad) else 0.55 if on else 0.18
        (x1, y1), (x2, y2) = pt(r, 180 - (g - 1) * 45 - 1.5), pt(r, 180 - g * 45 + 1.5)
        parts.append(f'<path d="M{x1:.1f} {y1:.1f} A{r} {r} 0 0 1 {x2:.1f} {y2:.1f}" '
                     f'stroke="{GRADE_COLOR[g]}" stroke-opacity="{op}" stroke-width="26" fill="none"/>')
        ac = 180 - (g - 0.5) * 45
        tx, ty = pt(r, ac)
        txt = '#fff' if op >= 0.55 else GRADE_COLOR[g]
        parts.append(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" dominant-baseline="central" '
                     f'font-size="11" font-weight="700" fill="{txt}" fill-opacity="{1 if op >= 0.55 else 0.75}" '
                     f'transform="rotate({90 - ac:.1f} {tx:.1f} {ty:.1f})">{weather.GRADE_NAME[g]}</text>')
    col = GRADE_COLOR.get(grade, T['muted'])
    disc, label_col = (col, '#fff') if bad else ('#EEF1F4', col)
    (dx1, dy1), (dx2, dy2) = pt(50, 180), pt(50, 0)
    parts.append(f'<path d="M{dx1:.1f} {dy1:.1f} A50 50 0 0 1 {dx2:.1f} {dy2:.1f} Z" fill="{disc}"/>')
    if grade:
        ac = 180 - (grade - 0.5) * 45
        (tx, ty), (b1x, b1y), (b2x, b2y) = pt(66, ac), pt(54, ac + 8), pt(54, ac - 8)
        parts.append(f'<polygon points="{tx:.1f},{ty:.1f} {b1x:.1f},{b1y:.1f} {b2x:.1f},{b2y:.1f}" '
                     f'fill="#1A1F27" fill-opacity="{1 if bad else 0.55}"/>')
    label = weather.GRADE_NAME.get(grade, '측정 없음')
    parts.append(f'<text x="100" y="92" text-anchor="middle" font-size="{20 if grade else 13}" '
                 f'font-weight="800" fill="{label_col}">{label}</text>')
    return f'<svg viewBox="0 0 200 106" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


def station_of(site, valid):
    """사업장 → 가까운 측정소 이름. valid: 측정값이 있는 측정소 이름 목록"""
    m = re.search(r'\((\S+?)동\)', site['addr']) or re.match(r'(\S+?)동', site['addr'])
    st = DONG_STATION.get(m.group(1)) if m else None
    if st not in valid:
        st = '검단' if site['gu'] == '검단구' else '연희'
    if st not in valid and valid:
        st = valid[0]
    return st

def draw():
    ui.add_head_html(CSS)
    data = geo.load()
    layers, shown, bound = {}, {}, set()
    view = {'ready': False, 'sel': '__start__', 'found': None, 'tab': '전체', 'pick': None,
            'page': 'map', 'ack': set()}
    refs = {}

    def counts():
        cnt = {k: 0 for k in STATUS_ORDER}
        for sid in S.state.sites:
            cnt[S.site_status(sid)] += 1
        return cnt

    # ── 페이지 전환 (사업장 지도 / 기상·환경) ──
    def set_page(p):
        view['page'] = p
        refs['wrap'].set_visibility(p == 'map')
        refs['env'].set_visibility(p == 'env')
        for k in ('zone', 'handle', 'side'):
            if k in refs:
                refs[k].set_visibility(p == 'map')
        if p == 'map' and view['ready']:
            m.run_map_method('invalidateSize')
        refs['tabs'].refresh()
        if 'alerts' in refs:
            refs['alerts'].refresh()

    def go_site(sid):
        """기상·환경 → 지도로 전환 후 해당 사업장 확대"""
        set_page('map')
        if 'focus' in refs:
            refs['focus'](sid)

    def build_tabs():
        with ui.element('div').classes('s2-ptabs'):
            for key, label, icon in [('map', '사업장 지도', 'map'), ('env', '기상·환경', 'wb_cloudy')]:
                tab = ui.element('div').classes('s2-ptab' + (' on' if view['page'] == key else ''))
                tab.on('click', lambda e, k=key: set_page(k))
                with tab:
                    ui.icon(icon)
                    ui.label(label)
                    if key == 'env' and all_alerts():
                        ui.element('div').classes('s2-ptab-dot')

    # ── 기상·환경 페이지 ──
    def warn_band(ws, al):
        """기상특보 띠: 발효 시 연한 빨강 + 빨간 굵은 글씨. 오른쪽에 환경 경보 칩"""
        others = [a for a in al if not a[1].startswith('기상특보')]
        band = ui.element('div').classes('s2-band alert' if ws else 's2-band calm')
        with band:
            ui.icon('campaign')
            if ws:
                ui.html('<b>기상특보 발효 중</b>')
                for w in ws:
                    ui.html(f"<b>{w['kind']}</b> · {w['regions']}")
            else:
                ui.label(f'발효 중인 기상특보 없음 ({config.WARN_REGION})')
            ui.space()
            if not others:
                ui.label('환경 경보 없음').style('font-size:17px;font-weight:400')
            for lvl, txt in others:
                ui.html(f'<span class="s2-achip" style="--c:{LEVEL_COLOR[lvl]}">{txt}</span>')

    def hero(d):
        """현재 날씨: 서해구 │ 검단구 반반 + 아래 요약 문장"""
        ws, fc = d['weather'], d['forecast']
        if not ws:
            return
        sky = fc[0]['sky'] if fc else 1
        with ui.element('div').classes('sg-panel s2-hero'):
            with ui.element('div').classes('s2-halves'):
                for w in ws[:2]:
                    hot = w['temp'] >= config.HEAT_TEMP
                    with ui.element('div').classes('s2-half'):
                        with ui.row().classes('w-full items-center no-wrap'):
                            ui.label(w['name']).classes('s2-hname')
                            ui.space()
                            ui.label(f"{w['time']} 관측").classes('s2-cap')
                        with ui.row().classes('items-center no-wrap gap-6'):
                            ui.label(sky_emoji(sky, w['pty'])).classes('s2-emo').style('font-size:92px')
                            ui.html(f'<span class="s2-temp" style="color:{C["alarm"] if hot else T["text"]}">'
                                    f'{w["temp"]:.1f}<sup>℃</sup></span>')
                            with ui.column().classes('gap-1'):
                                ui.label(sky_name(sky, w['pty'])).style('font-size:28px;font-weight:650')
                                ui.label(f"습도 {w['hum']:.0f}% · 풍속 {w['wind']:.1f}m/s").classes('s2-cap')
            emo, col, html = summary_text(d)
            ui.html(f'<div class="s2-summary" style="--c:{col}"><span class="s2-emo" style="font-size:44px">{emo}</span>'
                    f'<span>{html}</span></div>').classes('w-full')

    def tiles(d):
        w = d['weather'][0] if d['weather'] else None
        air = d['air']

        def worst(key):
            xs = [a for a in air if a[key] is not None]
            return max(xs, key=lambda a: a[key]) if xs else None

        p10, p25, o3 = worst('pm10'), worst('pm25'), worst('o3')
        items = [   # (아이콘, 이름, 값, 강조색, 보조 설명)
            ('water_drop', '습도', f"{w['hum']:.0f}%" if w else '-', None, w['name'] if w else ''),
            ('air', '풍속', f"{w['wind']:.1f}m/s" if w else '-',
             C['warn'] if w and w['wind'] >= config.WIND_MS else None, f'강풍 기준 {config.WIND_MS}m/s'),
            ('umbrella', '강수 (1시간)', f"{w['rain']:.1f}mm" if w else '-',
             C['info'] if w and w['pty'] else None, weather.PTY_NAME.get(w['pty'], '') if w else ''),
            ('grain', '미세먼지 PM10', f"{p10['pm10']:g}㎍" if p10 else '-',
             GRADE_COLOR.get(p10['pm10_grade']) if p10 else None,
             f"최고 · {p10['station']} · {weather.GRADE_NAME.get(p10['pm10_grade'], '-')}" if p10 else ''),
            ('blur_on', '초미세먼지 PM2.5', f"{p25['pm25']:g}㎍" if p25 else '-',
             GRADE_COLOR.get(p25['pm25_grade']) if p25 else None,
             f"최고 · {p25['station']} · {weather.GRADE_NAME.get(p25['pm25_grade'], '-')}" if p25 else ''),
            ('wb_twilight', '오존', f"{o3['o3']:g}ppm" if o3 else '-', None,
             f"최고 · {o3['station']}" if o3 else ''),
        ]
        with ui.element('div').classes('s2-tiles'):
            for icon, name, value, col, sub in items:
                with ui.element('div').classes('s2-tile').style(f"--c:{col or B['blue']}"):
                    with ui.element('div').classes('s2-tile-top'):
                        ui.icon(icon)
                        ui.label(name)
                    ui.label(value).classes('s2-tile-v').style(f'color:{col}' if col else '')
                    ui.label(sub).classes('s2-tile-s')

    def air_box(air):
        """측정소별 반원 게이지 + 배정 사업장. 순서 고정 · 측정값이 없어도 칸 표시 (칩 클릭 = 지도에서 위치 보기)"""
        by_name = {a['station']: a for a in air}
        names = STATION_ORDER + [n for n in by_name if n not in STATION_ORDER]
        groups = {n: [] for n in names}
        for s in sorted(S.state.sites.values(), key=lambda x: x['name']):
            st = station_of(s, names)
            if st in groups:
                groups[st].append(s)
        with ui.element('div').classes('sg-panel s2-box'):
            with ui.element('div').classes('s2-box-title'):
                ui.icon('air')
                ui.label('사업장별 대기질')
                ui.label('가까운 측정소 기준 · 등급 = PM10·PM2.5 중 나쁜 쪽').classes('r')
            with ui.element('div').classes('s2-gauges'):
                for n in names:
                    a = by_name.get(n) or {}
                    sites = groups[n]
                    ok = a.get('pm10') is not None or a.get('pm25') is not None
                    g = max(a.get('pm10_grade') or 0, a.get('pm25_grade') or 0) if ok else 0
                    with ui.element('div').classes('s2-gauge' + (' bad' if g >= 3 else '')) \
                            .style(f'--c:{GRADE_COLOR.get(g, T["muted"])}'):
                        with ui.row().classes('w-full items-center no-wrap'):
                            ui.label(f'{n} 측정소').classes('s2-gauge-t')
                            ui.space()
                            ui.label(f'사업장 {len(sites)}곳').classes('s2-tile-s')
                        if g:
                            ui.html(gauge_svg(g)).classes('w-full')
                        else:
                            ui.html('<div class="s2-gvals" style="padding:70px 0;font-size:22px">측정값 없음</div>')
                        if ok:
                            p10 = '-' if a['pm10'] is None else f"{a['pm10']:g}"
                            p25 = '-' if a['pm25'] is None else f"{a['pm25']:g}"
                            ui.html(f'<div class="s2-gvals">PM10 <b>{p10}</b>㎍ · PM2.5 <b>{p25}</b>㎍ · {a.get("time", "")}</div>')
                        with ui.element('div').classes('s2-gchips'):
                            for s in sites:
                                ch = ui.label(s['name']).classes('s2-gchip')
                                ch.on('click', lambda e, sid=s['id']: go_site(sid))
                            if not sites:
                                ui.label('배정 사업장 없음').classes('s2-tile-s')

    def hourly(fc):
        with ui.element('div').classes('sg-panel s2-box'):
            with ui.element('div').classes('s2-box-title'):
                ui.icon('schedule')
                ui.label('시간별 예보')
                ui.label(f"{config.WEATHER_POINTS[0]['name']} · 6시간").classes('r')
            for f in fc:
                with ui.element('div').classes('s2-hour' + (' rain' if f['pty'] else '')):
                    ui.label(f['time']).classes('s2-hour-t mono')
                    ui.label(sky_emoji(f['sky'], f['pty'])).classes('s2-emo').style('font-size:40px')
                    ui.label(sky_name(f['sky'], f['pty'])).classes('s2-hour-n')
                    temp = '-' if f['temp'] is None else f"{f['temp']:g}"
                    ui.html(f'<span class="s2-hour-temp mono">{temp}<sup>℃</sup></span>')
                    rain = '-' if f['rain'] in ('강수없음', None) else f['rain']
                    ui.label(f'강수 {rain}').classes('s2-hour-r')

    def impact_box(conds):
        """조건별 점검 대상 사업장 (사업장 칩 클릭 = 지도에서 위치 보기)"""
        with ui.element('div').classes('sg-panel s2-box'):
            with ui.element('div').classes('s2-box-title'):
                ui.icon('domain')
                ui.label('영향 사업장 · 조치')
            rules = [r for r in config.WEATHER_IMPACT if r['when'] in conds]
            if not rules:
                with ui.element('div').classes('s2-ok'):
                    ui.icon('check_circle').style('font-size:26px')
                    ui.label('현재 기상 조건으로 점검이 필요한 사업장 없음')
            for r in rules:
                sites = [s for s in S.state.sites.values()
                         if any(w in s['name'] or w in s['dept'] for w in r['match'])]
                with ui.element('div').classes('s2-impact'):
                    with ui.row().classes('items-center no-wrap gap-3'):
                        ui.html(f'<span class="s2-pill" style="--c:{C["warn"]};font-size:16px">{r["when"]}</span>')
                        ui.label(conds[r['when']]).style('font-size:19px;font-weight:650')
                    ui.label(r['action']).classes('s2-impact-act')
                    if not sites:
                        ui.label('해당 사업장 없음').classes('sg-muted')
                    with ui.element('div').classes('s2-chips'):
                        for s in sites:
                            ch = ui.label(s['name']).classes('s2-sitechip')
                            ch.on('click', lambda e, sid=s['id']: go_site(sid))

    def build_env():
        d = weather.data
        with ui.row().classes('w-full items-center no-wrap gap-4'):
            ui.label('기상·환경 현황').classes('s2-h1')
            if d['demo']:
                ui.label(d['error']) \
                    .classes('s2-demo')
            ui.space()
            ui.label(f"갱신 {S.hm(d['updated'])} · {config.WEATHER_REFRESH_MIN}분마다 확인" if d['updated']
                     else '불러오는 중').classes('sg-muted').style('font-size:18px')
        warn_band(d['warnings'], weather.alerts())
        with ui.element('div').classes('s2-env-grid'):
            with ui.element('div').style('grid-area:hero'):
                hero(d)
            with ui.element('div').style('grid-area:hour'):
                hourly(d['forecast'])
            with ui.element('div').style('grid-area:tiles'):
                tiles(d)
            with ui.element('div').style('grid-area:impact'):
                impact_box(weather.conditions())
            with ui.element('div').style('grid-area:air'):
                air_box(d['air'])
        ui.label('출처: 기상청 단기예보 조회서비스(초단기실황·초단기예보) · 기상청 기상특보 조회서비스 · '
                 '한국환경공단 에어코리아 대기오염정보 (공공데이터포털)').classes('s2-src')

    # ── 화면 틀 ──
    with screen_root():
        with header('지도', left=lambda: refs.__setitem__('tabs', live(build_tabs, every=30))):
            clock()

        refs['wrap'] = wrap = ui.element('div').classes('s2-wrap')
        refs['env'] = env = ui.element('div').classes('s2-envwrap')
        env.set_visibility(False)
        with env:
            live(build_env, every=30)

        if not data:
            with wrap:
                ui.label('지도 데이터가 없습니다. 터미널에서 python geo.py 를 한 번 실행한 뒤 서버를 다시 켜세요.') \
                    .classes('s2-empty sg-muted')
            return
        gj, coords = data
        feats = [f for f in gj['features'] if f['properties']['sggnm'] in GU_STYLE]
        bb = geo.bounds({'features': feats})

        # ── 지도 동작 ──
        def go_home():
            m.run_map_method('flyToBounds', bb, {'padding': [30, 30], 'duration': 1.0})

        def refresh_side():
            refs['list'].refresh()
            refs['card'].refresh()

        def focus_site(sid):
            """목록·검색·영향 사업장 선택: 이 화면에서만 이동 (다른 화면은 바뀌지 않음)"""
            view['found'] = sid
            c = coords.get(sid)
            if c:
                m.run_map_method('flyTo', [c['lat'], c['lng']], 16, {'duration': 1.0})
                refresh_pins()
                layers[sid].run_method('openTooltip')
            else:
                ui.notify('좌표가 없는 사업장입니다. 위치 지정을 해 주세요', type='warning')
            refresh_side()

        refs['focus'] = focus_site

        def clear_found():
            view['found'] = view['pick'] = None
            m.classes(remove='picking')
            refresh_pins()
            refresh_side()
            if not S.state.selected_site:
                go_home()

        def reset_view():
            """검색어·상태 필터·사업장 선택·위치 지정 초기화 후 전체 보기 (화면1 선택은 유지)"""
            view['found'] = view['pick'] = None
            view['tab'] = '전체'
            m.classes(remove='picking')
            q.set_value('')
            for layer in layers.values():
                layer.run_method('closeTooltip')
            refresh_pins()
            refresh_side()
            refs['chips'].refresh()
            go_home()

        def set_tab(t):
            view['tab'] = t
            refresh_pins()
            refresh_side()
            if 'chips' in refs:
                refs['chips'].refresh()

        def start_pick(sid):
            view['pick'] = sid
            m.classes(add='picking')
            refresh_side()

        def cancel_pick():
            view['pick'] = None
            m.classes(remove='picking')
            refresh_side()

        def on_map_click(e):
            sid = view['pick']
            if not sid:
                return
            ll = e.args['latlng']
            coords[sid] = geo.save_coord(sid, ll['lat'], ll['lng'])
            if sid in layers:
                layers[sid].run_method('setLatLng', [coords[sid]['lat'], coords[sid]['lng']])
            view['pick'] = None
            m.classes(remove='picking')
            refresh_pins()
            refresh_side()
            ui.notify(f"{S.state.sites[sid]['name']} 위치 저장 완료", type='positive')

        def ack(text):
            view['ack'].add(text)
            refs['alerts'].refresh()

        # ── 지도 + 지도 위 요소 ──
        with wrap:
            with ui.element('div').classes('s2-unzoom'):
                m = ui.leaflet(center=config.MAP_CENTER, zoom=config.MAP_ZOOM,
                               options={'zoomSnap': 0.25, 'zoomDelta': 0.5}) \
                    .classes('s2-map').style('width:100%;height:100%')
            m.on('map-click', on_map_click)

            def build_chips():
                """왼쪽 위 상태 칩: 개수 표시 + 클릭 = 필터"""
                cnt = counts()
                with ui.element('div').classes('s2-chipbar'):
                    for t in TABS:
                        n = len(S.state.sites) if t == '전체' else cnt[t]
                        col = B['blue'] if t == '전체' else S.STATUS_COLOR[t]
                        chip = ui.element('div').classes('s2-fchip' + (' on' if view['tab'] == t else '')) \
                            .style(f'--c:{col}')
                        chip.on('click', lambda e, x=t: set_tab(x))
                        with chip:
                            if t != '전체':
                                ui.element('span').classes('d')
                            ui.label(t)
                            ui.label(str(n)).classes('n')
                    ui.element('div').classes('s2-sep')
                    reset = ui.element('div').classes('s2-fchip s2-reset')
                    reset.on('click', lambda e: reset_view())
                    with reset:
                        ui.icon('restart_alt')
                        ui.label('초기화')

            refs['chips'] = live(build_chips, every=30)

            with ui.element('div').classes('sg-panel s2-legend'):
                for gu in GU_STYLE:
                    with ui.row().classes('items-center gap-3 no-wrap'):
                        ui.element('div').classes('s2-swatch').style(GU_SWATCH[gu])
                        ui.label(gu)
                for k in STATUS_ORDER:
                    with ui.row().classes('items-center gap-3 no-wrap'):
                        ui.element('div').classes('s2-dot').style(f'background:{S.STATUS_COLOR[k]}')
                        ui.label(k)

            def build_focus():
                """화면1에서 고른 상황 (가운데 위)"""
                sid = S.state.selected_site
                inc = S.get_incident(S.state.selected_incident) if S.state.selected_incident else None
                if not sid:
                    return
                with ui.element('div').classes('sg-panel s2-focus'):
                    ui.icon('my_location').style(f"font-size:24px;color:{B['blue']}")
                    ui.label('화면1 선택').classes('sg-muted')
                    text = S.state.sites[sid]['name'] + (f" · {inc['type']}" if inc else '')
                    ui.label(text).style('font-weight:650')
                    ui.button('전체 보기', on_click=lambda: S.select_incident(None)) \
                        .props('unelevated dense no-caps') \
                        .style(f"background:{B['blue']}14 !important;color:{B['blue']} !important;font-size:15px;padding:2px 14px")

            live(build_focus)

            def build_alerts():
                """환경·설비 이상 알림 창 (이상이 있고 확인 전일 때만)"""
                items = [a for a in all_alerts() if a[1] not in view['ack']]
                if not items or view['page'] != 'map':
                    return
                with ui.element('div').classes('sg-panel s2-alert'):
                    with ui.row().classes('w-full items-center no-wrap gap-2'):
                        ui.icon('warning').style(f"font-size:26px;color:{C['warn']}")
                        ui.label('환경·설비 이상').style('font-size:19px;font-weight:700')
                        ui.space()
                        ui.button('기상·환경 보기', on_click=lambda: set_page('env')) \
                            .props('unelevated dense no-caps') \
                            .style(f"background:{B['blue']} !important;color:#fff !important;font-size:14px;padding:2px 14px")
                    for lvl, txt in items:
                        with ui.element('div').classes('s2-alert-row'):
                            ui.element('div').classes('s2-dot').style(f'background:{LEVEL_COLOR[lvl]}')
                            ui.label(txt)
                            ui.space()
                            ui.button('확인', on_click=lambda e, t=txt: ack(t)).props('flat dense no-caps') \
                                .style(f"color:{B['blue']}")

            refs['alerts'] = live(build_alerts, every=30)

        # ── 오른쪽 검색 패널 ──
        def build_list():
            text = (q.value or '').strip()
            sites = sorted(S.state.sites.values(),
                           key=lambda s: (STATUS_ORDER.index(S.site_status(s['id'])), s['name']))
            if view['tab'] != '전체':
                sites = [s for s in sites if S.site_status(s['id']) == view['tab']]
            if text:
                sites = [s for s in sites if text in s['name'] or text in s['dept']
                         or text in s['addr'] or text in s['gu']]
            refs['hits'] = sites
            ui.label(f"필터 · {view['tab']} {len(sites)}곳 (지도 위 칩으로 변경)").classes('s2-filter')
            with ui.element('div').classes('s2-list'):
                if not sites:
                    ui.label('해당 사업장 없음').classes('sg-muted').style('font-size:16px;padding:12px')
                for s in sites:
                    st = S.site_status(s['id'])
                    on = s['id'] in (view['found'], S.state.selected_site)
                    item = ui.element('div').classes('s2-item' + (' on' if on else ''))
                    item.on('click', lambda e, sid=s['id']: focus_site(sid))
                    with item:
                        ui.element('div').classes('s2-dot').style(f'background:{S.STATUS_COLOR[st]}')
                        with ui.column().classes('gap-0'):
                            ui.label(s['name']).classes('s2-item-name')
                            ui.label(reason(s['id'])).classes('s2-item-sub').style(
                                f'color:{S.STATUS_COLOR[st]}' if st in ('미조치', '이상') else '')
                        ui.space()
                        if coords.get(s['id'], {}).get('approx'):
                            ui.label('근사').classes('s2-item-sub')

        def build_card():
            """선택 사업장 카드: 주소 · 위치 지정 · 인접 사업장"""
            sid = view['found'] or S.state.selected_site
            if not sid or sid not in S.state.sites:
                return
            s = S.state.sites[sid]
            st = S.site_status(sid)
            c = coords.get(sid)
            with ui.element('div').classes('s2-card'):
                with ui.row().classes('w-full items-center no-wrap gap-2'):
                    ui.element('div').classes('s2-dot').style(f'background:{S.STATUS_COLOR[st]}')
                    ui.label(s['name']).style('font-size:19px;font-weight:700')
                    ui.space()
                    if view['found']:
                        ui.button(icon='close', on_click=clear_found).props('flat dense round')
                ui.label(config.full_addr(s)).classes('s2-item-sub')
                if view['pick'] == sid:
                    with ui.row().classes('w-full items-center no-wrap'):
                        ui.label('지도에서 실제 위치를 클릭하세요').style(f"color:{C['alarm']};font-weight:650")
                        ui.space()
                        ui.button('취소', on_click=cancel_pick).props('flat dense no-caps')
                else:
                    with ui.row().classes('w-full items-center no-wrap'):
                        if c and c.get('approx'):
                            ui.label('위치 근사값').style(f"color:{C['warn']};font-weight:650")
                        ui.space()
                        ui.button('지도에서 위치 지정', on_click=lambda: start_pick(sid)) \
                            .props('unelevated dense no-caps') \
                            .style(f"background:{B['blue']}14 !important;color:{B['blue']} !important;font-size:14px;padding:2px 12px")
                if c:
                    ui.label('인접 사업장').classes('s2-card-sub')
                    near = sorted((dist_km(c, coords[o]), o) for o in S.state.sites
                                  if o != sid and o in coords)[:3]
                    for d, o in near:
                        ost = S.site_status(o)
                        row = ui.element('div').classes('s2-near')
                        row.on('click', lambda e, x=o: focus_site(x))
                        with row:
                            ui.element('div').classes('s2-dot').style(f'background:{S.STATUS_COLOR[ost]}')
                            ui.label(S.state.sites[o]['name'])
                            ui.space()
                            ui.label(f'{d:.1f}km').classes('mono').style('font-weight:650')

        def search_enter():
            if refs.get('hits'):
                focus_site(refs['hits'][0]['id'])

        refs['zone'] = ui.element('div').classes('s2-side-zone')
        with ui.element('div').classes('s2-handle') as handle:
            ui.icon('search').style('font-size:22px')
            ui.label('사업장 검색')
        refs['handle'] = handle
        with ui.element('div').classes('s2-side') as side:
            ui.label('사업장 찾기').classes('s2-side-title')
            q = ui.input(placeholder='이름 · 부서 · 주소 · 구').props('outlined clearable').classes('w-full') \
                .style('font-size:18px')
            q.on_value_change(lambda e: refs['list'].refresh())
            q.on('keydown.enter', search_enter)
            refs['list'] = live(build_list, every=30)
            refs['card'] = live(build_card)
        refs['side'] = side

        # ── 마커 갱신 (바뀐 곳만) ──
        def refresh_pins():
            if not view['ready']:
                return
            sel = S.state.selected_site
            for sid, layer in layers.items():
                st = S.site_status(sid)
                incs = S.open_incidents(sid)
                high = any(S.is_high(i) for i in incs)
                cnt = len(incs)
                on = sid in (sel, view['found'])
                visible = on or view['tab'] in ('전체', st)
                key = (st, on, visible, high, cnt)
                html = tip_html(sid, coords[sid].get('approx'))
                prev = shown.get(sid)
                if prev is None or prev[0] != key:
                    layer.run_method(':setIcon', pin_icon(st, on, high, cnt))
                    layer.run_method('setOpacity', 1 if visible else 0.2)
                    z = 3000 if on else 2000 if (high and st == '미조치') else {'미조치': 1000, '이상': 500}.get(st, 0)
                    layer.run_method('setZIndexOffset', z)
                if prev is None or prev[1] != html:
                    if sid in bound:
                        layer.run_method('setTooltipContent', html)
                    else:
                        layer.run_method('bindTooltip', html, TIP_OPTIONS)
                        bound.add(sid)
                shown[sid] = (key, html)

            if sel != view['sel']:             # 화면1에서 고른 사업장으로 확대 / 해제 시 전체 보기
                view['sel'] = sel
                if sel and sel in coords:
                    if view['page'] != 'map':
                        set_page('map')
                    view['found'] = None
                    c = coords[sel]
                    m.run_map_method('flyTo', [c['lat'], c['lng']], 16, {'duration': 1.2})
                    layers[sel].run_method('openTooltip')
                elif not view['found']:
                    go_home()

        async def setup():
            await m.initialized()
            m.run_map_method('invalidateSize')     # 배율 보정 후 지도 크기 다시 계산
            for gu, style in GU_STYLE.items():
                part = [f for f in feats if f['properties']['sggnm'] == gu]
                if part:
                    m.generic_layer(name='geoJSON', args=[{'type': 'FeatureCollection', 'features': part},
                                                          {'style': style, 'interactive': False}])
            for s in config.SITES:
                c = coords.get(s['id'])
                if c:
                    layers[s['id']] = m.marker(latlng=(c['lat'], c['lng']))
            view['ready'] = True
            refresh_pins()

        ui.timer(0.3, setup, once=True)
        ui.timer(1, refresh_pins)