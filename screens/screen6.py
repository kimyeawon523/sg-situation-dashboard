"""화면6 · CCTV 상시 감시 — 4/6분할, 일정 간격 순환
ITS 실시간 영상만 표시(국가교통정보센터 공개 CCTV, 서해구·검단구 주변 도로).
키가 없거나 연결 전이면 '실시간 CCTV 연결 대기' 안내. 녹화 영상은 쓰지 않음."""
import time

from nicegui import ui

import config
import its
from screens import screen_root, header, B
from screens import cctv


def draw():
    ui.add_head_html(cctv.HEAD + cctv.CSS)
    view = {'n': list(config.GRID_OPTIONS.values())[0], 'page': 0, 'pages': 1, 'rotate': True, 'sig': None}
    pending = []

    @ui.refreshable
    def controls():
        with ui.row().classes('items-center gap-3 no-wrap'):
            for label, n in config.GRID_OPTIONS.items():
                on = view['n'] == n
                ui.button(label, on_click=lambda e, x=n: set_n(x)) \
                    .props('unelevated no-caps' if on else 'outline no-caps') \
                    .style(f"font-size:20px;{'background:' + B['blue'] + ' !important;color:#fff' if on else ''}")
            ui.button(f"순환 {'ON' if view['rotate'] else 'OFF'}", on_click=toggle_rotate) \
                .props('outline no-caps').style('font-size:20px')
            ui.label(f"{view['page'] % view['pages'] + 1}/{view['pages']} · {config.ROTATE_SEC}초") \
                .classes('sg-muted').style('font-size:20px')
            n_live, n_mine = len(its.data['cams']), len(cctv.sources('a'))
            ui.label(f'실시간 {n_mine}대 (전체 {n_live}대 중 화면6 몫)' if n_live
                     else f"연결 대기 ({its.data['error'] or '연결 중'})") \
                .classes('sg-muted').style('font-size:18px')

    @ui.refreshable
    def body():
        view['pages'] = cctv.grid(view['n'], view['page'], pending, part='a')

    def redraw():
        body.refresh()
        controls.refresh()
        cctv.flush(pending)

    def set_n(n):
        view['n'], view['page'] = n, 0
        redraw()

    def toggle_rotate():
        view['rotate'] = not view['rotate']
        controls.refresh()

    def rotate():
        if view['rotate'] and view['pages'] > 1:
            view['page'] += 1
            redraw()

    def watch_sources():
        """ITS 목록이 들어오거나 갱신되면(10분마다 영상 주소 재발급) 다시 그림"""
        if cctv.signature() != view['sig']:
            view['sig'] = cctv.signature()
            redraw()

    with screen_root():
        with header(config.SCREEN_NAMES[6]):
            controls()
            clock = ui.label().classes('mono').style('font-size:30px;font-weight:700')
        with ui.element('div').classes('sg-body'):
            body()

    ui.timer(1, lambda: clock.set_text(time.strftime('%Y.%m.%d %H:%M:%S')))
    ui.timer(0.5, lambda: (controls.refresh(), cctv.flush(pending)), once=True)
    ui.timer(2, watch_sources)
    ui.timer(config.ROTATE_SEC, rotate)