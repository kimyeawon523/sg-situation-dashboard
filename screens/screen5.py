"""화면5 · CCTV 이벤트 연동
평시: 화면6과 같은 4/6분할 ITS 실시간 영상, 일정 간격 순환. 화면6과 겹치지 않는 나머지 CCTV 표시
화면1에서 상황 선택 시(재난·긴급은 접수 즉시 자동): 팝업 창 — 해당 사업장 CCTV(시연용 녹화 영상) + 경보 정보
[실제 상황]·[오경보]만 이 화면에서 입력 (기록은 화면1 상황일지). 오경보는 이 화면에서 바로 종결."""
import time

from nicegui import ui

import config
import its
import state as S
from screens import screen_root, header, live, badge, T, C, B
from screens import cctv

PART = 'b'   # 화면6('a')과 겹치지 않는 CCTV 묶음

CSS = f"""
<style>
.s5-wrap {{ flex:1; min-height:0; width:100%; align-self:stretch; display:grid;
           grid-template-columns:1fr 560px; gap:20px; }}
.s5-frame {{ position:relative; border:10px solid; border-radius:14px; overflow:hidden; background:#0B0F14; }}
.s5-alarm {{ animation:s5-flash 1s steps(2,start) infinite; }}
@keyframes s5-flash {{ 50% {{ border-color:rgba(229,56,59,.25); }} }}
.s5-box {{ position:absolute; border:4px solid #E5383B; box-shadow:0 0 0 2px rgba(0,0,0,.35);
          animation:s5-box 1s steps(2,start) infinite; }}
@keyframes s5-box {{ 50% {{ opacity:.35; }} }}
.s5-box-tag {{ position:absolute; left:-4px; top:-38px; padding:4px 12px; background:#E5383B; color:#fff;
              font-size:20px; font-weight:700; white-space:nowrap; }}
.s5-water {{ position:absolute; right:18px; bottom:52px; padding:4px 12px; border-radius:6px;
            background:rgba(0,0,0,.5); color:#fff; font-size:18px; }}
.s5-side {{ display:flex; flex-direction:column; gap:16px; min-height:0; }}
.s5-info {{ padding:22px 26px; display:flex; flex-direction:column; gap:14px; }}
.s5-row {{ display:grid; grid-template-columns:130px 1fr; font-size:24px; padding:6px 0;
          border-bottom:1px solid {T['line']}; }}
.s5-row .k {{ color:{T['muted']}; }}
.s5-btns {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.s5-check {{ padding:12px 16px; border-radius:10px; font-size:22px; font-weight:700; }}
</style>
"""


def current():
    """화면1에서 선택된 진행 중 상황 (선택이 없으면 None → 팝업 없음)"""
    iid = S.state.selected_incident
    inc = S.get_incident(iid) if iid else None
    return inc if inc and not S.is_closed(inc) else None


def draw():
    ui.add_head_html(cctv.HEAD + cctv.CSS + CSS)
    view = {'n': list(config.GRID_OPTIONS.values())[0], 'page': 0, 'pages': 1, 'rotate': True,
            'sig': None, 'iid': '__start__', 'dismissed': None, 'confirm': None}
    pending = []

    # ── 오경보 확인 창 ──
    with ui.dialog() as confirm_dlg, ui.card().classes('sg-panel').style('min-width:760px;padding:28px 32px;gap:16px'):
        ui.label('오경보로 종결할까요?').style('font-size:30px;font-weight:900')
        ui.label('상황일지에 기록되고 보고서가 \'오경보\'로 자동 작성되며, 상황목록에서 사라집니다.') \
            .classes('sg-muted').style('font-size:21px')
        with ui.row().classes('w-full justify-end gap-3'):
            ui.button('취소', on_click=confirm_dlg.close).props('flat no-caps').style('font-size:20px')

            def do_false_alarm():
                if view['confirm']:
                    S.close_false_alarm(view['confirm'], S.state.operator)
                    ui.notify('오경보로 종결했습니다', type='positive')
                confirm_dlg.close()

            ui.button('오경보로 종결', on_click=do_false_alarm).props('unelevated no-caps') \
                .style(f"background:{C['unknown']} !important;color:#fff;font-size:20px")

    def ask_false_alarm(iid):
        view['confirm'] = iid
        confirm_dlg.open()

    # ── 팝업: 경보 정보 패널 ──
    def build_info(iid):
        inc = S.get_incident(iid)
        if not inc or S.is_closed(inc):
            return
        site = S.state.sites[inc['site']]
        with ui.element('div').classes('sg-panel s5-info'):
            with ui.row().classes('items-center gap-3 no-wrap'):
                ui.icon('notification_important').style(f"font-size:34px;color:{S.GRADE_COLOR[inc['grade']]}")
                ui.label('경보 정보').style('font-size:30px;font-weight:900')
            with ui.row().classes('items-start gap-3 no-wrap w-full'):
                with ui.element('div').style('flex-shrink:0;white-space:nowrap;margin-top:4px'):
                    badge(inc['grade'], S.GRADE_COLOR[inc['grade']], 26)
                ui.label(inc['type']).style(f"flex:1;min-width:0;font-size:34px;font-weight:900;line-height:1.25;"
                                            f"word-break:keep-all;color:{S.GRADE_COLOR[inc['grade']]}")
            rows = [('사업장', site['name']), ('위치', inc['loc']),
                    ('유형', inc['category'] + (f" · {inc['sub']}" if inc.get('sub') else '')),
                    ('발생 시각', S.md_hm(inc['start'])), ('경과', S.ago(inc['start'])),
                    ('접수 방식', inc['entry']), ('처리 단계', inc['stage'])]
            for k, v in rows:
                with ui.element('div').classes('s5-row'):
                    ui.label(k).classes('k')
                    ui.label(v).style('font-weight:700')
        with ui.element('div').classes('sg-panel s5-info'):
            ui.label('영상 확인').style('font-size:26px;font-weight:900')
            chk = inc.get('video_check')
            if chk:
                ui.label(f'{chk[0]} 확인 · {S.hm(chk[1])}').classes('s5-check') \
                    .style(f"background:{C['alarm']}14;color:{C['alarm']}")
                ui.label('이후 처리는 화면1에서 진행').classes('sg-muted').style('font-size:19px')
            else:
                ui.label('영상으로 실제 상황 여부를 확인하세요').classes('sg-muted').style('font-size:20px')
            with ui.element('div').classes('s5-btns'):
                ui.button('실제 상황', on_click=lambda: S.video_confirm(iid, S.state.operator)) \
                    .props('unelevated no-caps size=lg') \
                    .style(f"background:{C['alarm']} !important;color:#fff;font-size:22px")
                ui.button('오경보', on_click=lambda: ask_false_alarm(iid)) \
                    .props('unelevated no-caps size=lg') \
                    .style(f"background:{C['unknown']} !important;color:#fff;font-size:22px")
            ui.label('기록은 화면1 상황일지에 남음').classes('sg-muted').style('font-size:18px')

    # ── 팝업: 선택된 사업장 CCTV (시연용 녹화 영상) ──
    def event_view(inc):
        v = cctv.event_video(inc)
        if inc.get('video'):                                   # 엑셀 지정 영상 우선
            v = {**v, 'file': inc['video'], 'box': None}
        site = S.state.sites[inc['site']]
        high = S.is_high(inc)
        cam = f"CH{int(inc['site'][1:]):02d} {site['name']} {inc['loc']}"
        with ui.element('div').classes('s5-wrap'):
            frame = ui.element('div').classes('s5-frame' + (' s5-alarm' if high else '')) \
                .style(f"border-color:{C['alarm'] if high else C['warn']}")
            with frame:
                with ui.element('div').classes('cc-tile').style('position:absolute;inset:0;border-radius:0'):
                    if cctv.video_ok(v['file']):
                        cctv.video({'file': v['file']}, [])
                    else:
                        ui.label(f"영상 준비 중 (assets/videos/{v['file']})").classes('cc-empty') \
                            .style('position:absolute;inset:0')
                    ui.element('div').classes('cc-vignette')
                    if v.get('box'):
                        l, t, w, h = v['box']
                        with ui.element('div').classes('s5-box') \
                                .style(f'left:{l}%;top:{t}%;width:{w}%;height:{h}%'):
                            ui.label(f"{inc['type']} 감지").classes('s5-box-tag')
                    with ui.element('div').classes('cc-top'):
                        ui.label(cam).classes('cc-name')
                        ui.space()
                        with ui.element('div').classes('cc-badge cc-live'):
                            ui.element('div').classes('cc-dot')
                            ui.label('REC')
                    ui.label('시연용 녹화 영상 · 실제 공단 CCTV 아님').classes('s5-water')
                    with ui.element('div').classes('cc-bottom'):
                        ui.label(f"{inc['entry']} 접수 · {S.md_hm(inc['start'])} 발생")
                        ui.label().classes('cc-clock')
            with ui.element('div').classes('s5-side'):
                live(lambda: build_info(inc['id']), every=10)

    def dismiss():
        """화면5에서만 팝업 닫기 (화면1 선택은 유지)"""
        view['dismissed'] = view['iid']
        pop.close()
        controls.refresh()

    def reopen():
        view['dismissed'] = None
        pop_body.refresh()
        pop.open()
        controls.refresh()

    # ── 이벤트 팝업 창 ──
    with ui.dialog().props('persistent') as pop, ui.card().classes('sg-panel') \
            .style('width:2800px;max-width:2800px;height:1500px;max-height:1500px;padding:24px 28px;'
                   'gap:16px;display:flex;flex-direction:column'):

        @ui.refreshable
        def pop_body():
            inc = current()
            if not inc:
                return
            site = S.state.sites[inc['site']]
            with ui.row().classes('w-full items-center no-wrap gap-4'):
                ui.icon('videocam').style(f"font-size:40px;color:{S.GRADE_COLOR[inc['grade']]}")
                ui.label('CCTV 이벤트').style('font-size:32px;font-weight:900')
                badge(inc['grade'], S.GRADE_COLOR[inc['grade']], 26)
                ui.label(f"{site['name']} · {inc['type']}").style('font-size:30px;font-weight:700')
                ui.space()
                ui.button('분할 화면으로', icon='grid_view', on_click=dismiss) \
                    .props('outline no-caps').style('font-size:22px')
            event_view(inc)

        pop_body()

    # ── 제목줄: 화면6과 같은 분할·순환 조작 (+ 팝업을 닫았을 때 다시 보기) ──
    @ui.refreshable
    def controls():
        with ui.row().classes('items-center gap-3 no-wrap'):
            inc = current()
            if inc and view['dismissed'] == inc['id']:
                ui.button('이벤트 보기', icon='notification_important', on_click=reopen) \
                    .props('unelevated no-caps') \
                    .style(f"background:{S.GRADE_COLOR[inc['grade']]} !important;color:#fff;font-size:20px")
            for label, n in config.GRID_OPTIONS.items():
                on = view['n'] == n
                ui.button(label, on_click=lambda e, x=n: set_n(x)) \
                    .props('unelevated no-caps' if on else 'outline no-caps') \
                    .style(f"font-size:20px;{'background:' + B['blue'] + ' !important;color:#fff' if on else ''}")
            ui.button(f"순환 {'ON' if view['rotate'] else 'OFF'}", on_click=toggle_rotate) \
                .props('outline no-caps').style('font-size:20px')
            ui.label(f"{view['page'] % view['pages'] + 1}/{view['pages']} · {config.ROTATE_SEC}초") \
                .classes('sg-muted').style('font-size:20px')
            n_live, n_mine = len(its.data['cams']), len(cctv.sources(PART))
            ui.label(f'실시간 {n_mine}대 (전체 {n_live}대 중 화면5 몫)' if n_live
                     else f"연결 대기 ({its.data['error'] or '연결 중'})") \
                .classes('sg-muted').style('font-size:18px')

    @ui.refreshable
    def body():
        view['pages'] = cctv.grid(view['n'], view['page'], pending, part=PART)

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

    def watch():
        """화면1에서 상황을 누를 때마다 팝업 열기 (같은 상황을 다시 눌러도 열림) · 선택 해제·종결 시 닫기
        ITS 목록 변화 → 분할 화면 다시 그림"""
        inc = current()
        iid = inc['id'] if inc else None
        seq = getattr(S.state, 'select_seq', 0)
        if iid != view['iid'] or seq != view.get('seq'):
            view['iid'], view['seq'], view['dismissed'] = iid, seq, None
            if iid:
                pop_body.refresh()
                pop.open()
            else:
                pop.close()
            controls.refresh()
        if cctv.signature() != view['sig']:
            view['sig'] = cctv.signature()
            redraw()

    with screen_root():
        with header(config.SCREEN_NAMES[5]):
            controls()
            clock = ui.label().classes('mono').style('font-size:30px;font-weight:700')
        with ui.element('div').classes('sg-body'):
            body()

    ui.timer(1, lambda: clock.set_text(time.strftime('%Y.%m.%d %H:%M:%S')))
    ui.timer(0.5, lambda: (controls.refresh(), cctv.flush(pending)), once=True)
    ui.timer(0.5, watch)
    ui.timer(config.ROTATE_SEC, rotate)