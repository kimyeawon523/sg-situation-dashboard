"""메인 화면: 시그니처 + 비전 + 화면 6개 바로가기"""
from nicegui import app, ui

import config
from screens import T, B, BRAND_BAR, ICONS, fit_zoom

DESC = {1: '금일 접수·미조치 현황과 상황목록, 처리 단계 확인',
        2: '전 사업장 위치와 상태(정상·이상·미조치)를 지도에서 확인',
        3: '연계 사업장 설비 경보, 미연계 사업장 보고 상태 확인',
        4: '사업장 담당자 호출·응답 상태와 차순위 호출',
        5: '경보 발생 위치 영상 자동 표출, 오경보·심각도 확인',
        6: '수영장 등 고위험 구역 분할 영상 순환 감시'}
TILE_COLORS = [B['sky'], B['blue'], B['lime']]   # 열마다 심볼 3색 순환

CSS = f"""
<style>
.hm {{ width:100%; min-height:var(--sg-h, 100vh); display:flex; flex-direction:column; background:{T['bg']}; }}
.hm-bar {{ height:6px; flex-shrink:0; background:{BRAND_BAR}; }}
.hm-vision b {{ color:{B['blue']}; }}
.op-chip {{ display:flex; align-items:center; gap:8px; padding:8px 20px; border-radius:999px;
           background:{T['panel']}; border:1px solid {T['line']}; font-size:18px; font-weight:700;
           color:{B['blue']}; }}
.ha-hero {{ display:flex; flex-direction:column; align-items:center; gap:14px; padding:56px 0 36px; }}
.ha-sign {{ height:76px; }}
.ha-title {{ font-size:54px; font-weight:900; color:{T['text']}; }}
.ha-title b {{ color:{B['blue']}; }}
.ha-label {{ font-size:15px; font-weight:700; letter-spacing:.25em; color:{B['blue']}; }}
.ha-vision {{ font-size:26px; font-weight:700; color:{T['text']}; }}
.ha-grid {{ align-self:center; display:grid; grid-template-columns:repeat(3,460px); gap:20px 32px;
           padding:12px 0 48px; }}
.ha-tile {{ display:flex; gap:20px; padding:24px; border-radius:16px; cursor:pointer;
           background:{T['panel']}; border:1px solid {T['line']}; transition:all .15s;
           box-shadow:0 1px 3px rgba(16,24,40,.04); }}
.ha-tile:hover {{ transform:translateY(-2px); box-shadow:0 10px 24px rgba(16,24,40,.08); }}
.ha-icon {{ width:76px; height:76px; border-radius:50%; flex-shrink:0; display:flex;
           align-items:center; justify-content:center; }}
</style>
"""


def go(n):
    return lambda e: ui.navigate.to(f'/screen/{n}')


def operator_chip(name):
    with ui.element('div').classes('op-chip'):
        ui.icon('account_circle').style('font-size:24px')
        ui.html(f'<span style="color:{T["text"]};font-weight:500">관제사 </span>{name}'
                f'<span style="color:{T["text"]};font-weight:500"> 근무 중</span>')


def draw():
    ui.add_head_html(CSS)
    fit_zoom(config.HOME_ZOOM)
    name = app.storage.user.get('name', 'OOO')

    with ui.element('div').classes('hm'):
        ui.element('div').classes('hm-bar')

        # 상단: 시그니처 + 제목 + 비전 + 관제자
        with ui.element('div').classes('ha-hero'):
            ui.html('<img src="/assets/logo_full.png" class="ha-sign">')
            ui.html('<div class="ha-title">SG 상황센터 <b>통합관제</b></div>')
            ui.label('VISION').classes('ha-label')
            ui.html(f'<div class="ha-vision hm-vision">{config.VISION_HTML}</div>')
            operator_chip(name)

        # 화면 6개 바로가기 (윗줄 1·2·3, 아랫줄 4·5·6)
        with ui.element('div').classes('ha-grid'):
            for n in range(1, 7):
                color = TILE_COLORS[(n - 1) % 3]
                with ui.element('div').classes('ha-tile').on('click', go(n)):
                    with ui.element('div').classes('ha-icon').style(f'background:{color}1A'):
                        ui.icon(ICONS[n]).style(f'font-size:40px;color:{color}')
                    with ui.column().classes('gap-1'):
                        ui.label(config.SCREEN_NAMES[n]).style('font-size:28px;font-weight:900')
                        ui.label(DESC[n]).classes('sg-muted').style('font-size:17px')