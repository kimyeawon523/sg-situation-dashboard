# ── 표준 라이브러리 ──
import importlib
import os
import sys
import uuid
from pathlib import Path

# ── 실행 위치 고정 (exe·소스 공통: data/, assets/, 키 파일 기준 폴더) ──
BASE_DIR = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
            else os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

# ── 외부 라이브러리 ──
from fastapi.responses import RedirectResponse
from nicegui import app, ui

# ── 프로젝트 모듈 (chdir 이후에 import) ──
import config
import state as S
import weather
import its
from screens import apply_style, side_nav, screen_root, header, live
from screens import home, login
from screens import screen1, screen2, screen3, screen4, screen5, screen6  # exe 빌드 시 포함용


# assets 폴더를 /assets 주소로 연결 (로고 이미지)
app.add_static_files('/assets', str(Path(BASE_DIR) / 'assets'))

# 서버를 켤 때마다 새 접속 번호 생성 → 재시작하면 이전 로그인은 무효
SERVER_SESSION = uuid.uuid4().hex


def need_login():
    """로그인이 필요한데 아직 안 했으면 True (서버 재시작 전 로그인 기록은 무효)"""
    if not config.LOGIN_REQUIRED:
        return False
    user = app.storage.user
    return not (user.get('auth') and user.get('session') == S.SERVER_SESSION)

def get_draw(n):
    """screens/screenN.py 안의 draw 함수를 찾음. 아직 없으면 None."""
    module = importlib.import_module(f'screens.screen{n}')
    return getattr(module, 'draw', None)


def placeholder(n):
    """아직 만들지 않은 화면: 제목 + 공유 상태 확인용 숫자만 표시"""
    with screen_root():
        header(config.SCREEN_NAMES[n])
        with ui.column().classes('sg-body'):
            ui.label('준비 중').classes('sg-muted').style('font-size:24px')
            live(lambda: ui.label(str(S.summary())).style('font-size:24px'))


@ui.page('/login')
def login_page():
    if not need_login():
        return RedirectResponse('/')
    apply_style()
    login.draw()


@ui.page('/logout')
def logout_page():
    app.storage.user.clear()
    S.logout()
    return RedirectResponse('/login')


@ui.page('/')
def index():
    if need_login():
        return RedirectResponse('/login')
    apply_style()
    side_nav('home')
    home.draw()


@ui.page('/screen/{n}')
def screen(n: int):
    if need_login():
        return RedirectResponse('/login')
    apply_style()
    if n not in config.SCREEN_NAMES:
        ui.label('화면 번호는 1~6입니다.')
        return
    side_nav(n)
    draw = get_draw(n)
    if draw:
        draw()
    else:
        placeholder(n)


app.on_startup(weather.start)
app.on_startup(its.start)
app.on_startup(S.start_demo)     # 시나리오 불러오기 · 미연계 사업장 정기 보고 자동 접수


ui.run(title='SG 상황센터', dark=False, storage_secret='sg-dashboard-demo',
       reload=False, port=8080, show=True, host='0.0.0.0')