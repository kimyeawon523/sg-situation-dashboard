"""로그인 화면: 왼쪽 비전 / 오른쪽 입력창"""
from nicegui import app, ui

import config
import state as S
from screens import T, B, fit_zoom

CSS = f"""
<style>
.sg-lg {{ width:100%; height:var(--sg-h, 100vh); display:flex; }}
.lg-brand {{ flex:1.1; position:relative; overflow:hidden; color:#fff; display:flex;
            flex-direction:column; justify-content:flex-end; padding:80px;
            background:linear-gradient(140deg,{B['blue']} 0%,{B['sky']} 100%); }}
.lg-brand::after {{ content:''; position:absolute; left:0; right:0; bottom:0; height:10px;
                   background:{B['lime']}; }}
.lg-mark {{ position:absolute; right:-90px; top:-60px; width:640px; opacity:.13;
           filter:brightness(0) invert(1); }}
.lg-vision-label {{ font-size:20px; font-weight:700; letter-spacing:.25em; opacity:.85; }}
.lg-vision {{ font-size:48px; font-weight:900; line-height:1.35; margin-top:14px; }}
.lg-vision b {{ color:#E3F28C; }}
.lg-form-wrap {{ flex:1; display:flex; align-items:center; justify-content:center; background:{T['panel']}; }}
.lg-form {{ width:440px; display:flex; flex-direction:column; gap:16px; }}
.lg-sign {{ width:250px; margin-bottom:16px; }}
.lg-title {{ font-size:36px; font-weight:900; color:{T['text']}; }}
</style>
"""


def draw():
    ui.add_head_html(CSS)
    fit_zoom(config.HOME_ZOOM)
    with ui.element('div').classes('sg-lg'):

        # 왼쪽: 비전
        with ui.element('div').classes('lg-brand'):
            ui.html('<img src="/assets/logo.png" class="lg-mark">')   # 흰색 워터마크
            ui.label('VISION').classes('lg-vision-label')
            ui.html(f'<div class="lg-vision">{config.VISION_HTML}</div>')

        # 오른쪽: 로그인
        with ui.element('div').classes('lg-form-wrap'):
            with ui.element('div').classes('lg-form'):
                ui.html('<img src="/assets/logo_full.png" class="lg-sign">')
                ui.label('SG 상황센터 통합관제').classes('lg-title')
                ui.label('관제사 계정으로 로그인하세요.').classes('sg-muted').style('font-size:18px')
                uid = ui.input('아이디').props('outlined').classes('w-full')
                pw = ui.input('비밀번호', password=True, password_toggle_button=True) \
                    .props('outlined').classes('w-full')

                def try_login():
                    acc = config.ACCOUNTS.get((uid.value or '').strip().lower())
                    if not acc or acc['pw'] != pw.value:
                        ui.notify('아이디 또는 비밀번호가 올바르지 않습니다', type='negative')
                        return
                    # 이 브라우저에 로그인 기록 + 현재 서버 접속 번호 저장
                    app.storage.user.update(auth=True, name=acc['name'], session=S.SERVER_SESSION)
                    S.login(acc['name'])
                    ui.navigate.to('/')

                pw.on('keydown.enter', try_login)       # 비밀번호 입력 후 Enter로도 로그인
                ui.button('로그인', on_click=try_login).props('unelevated size=lg').classes('w-full') \
                    .style(f"background:{B['blue']} !important;color:#fff;height:56px;font-size:18px")
                ui.label('시연용 계정: admin / 1234').classes('sg-muted').style('font-size:14px')