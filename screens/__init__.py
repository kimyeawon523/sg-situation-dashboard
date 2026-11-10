"""화면 6개가 같이 쓰는 공통 도구."""
import time

from nicegui import ui

import config
import state as S

T = config.THEMES[config.THEME]
C = config.COLORS
B = config.BRAND

C_RED = '#E5383B'

BRAND_BAR = (f"linear-gradient(90deg,{B['sky']} 0 33.3%,{B['blue']} 33.3% 66.6%,"
             f"{B['lime']} 66.6% 100%)")

ICONS = {1: 'notifications_active', 2: 'map', 3: 'apartment',
         4: 'groups', 5: 'report', 6: 'videocam'}

# 위험 등급 색: (기준색, 글자색). 알림(노랑)은 흰 바탕에서 안 읽혀 글자만 진하게
GRADE_STYLE = {
    '재난': ('#8B0A1A', '#8B0A1A'),
    '긴급': ('#E5383B', '#D62F32'),
    '주의': ('#F08C00', '#C46F00'),
    '알림': ('#E9B200', '#9A7600'),
}
SOLID_GRADES = {'재난'}          # 채움 배지로 표시할 등급

# 사업장·건 상태 색 (점 + 글자 공통)
STATUS_COLOR = {
    '미조치': '#E5383B',
    '이상': '#F08C00',
    '보고 지연': '#F08C00',
    '확인 불가': '#6B7280',
    '정상': '#2EA043',
    '조치 완료': B['blue'],
    '보고 완료': '#6B7280',
}

STYLE = f"""
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
body {{ background:{T['bg']} !important; color:{T['text']};
       font-family:'Pretendard Variable',Pretendard,'Malgun Gothic',sans-serif;
       letter-spacing:-0.01em; }}
.nicegui-content {{ padding:0 !important; gap:0 !important; }}
.sg-screen {{ width:100%; height:var(--sg-h, 100vh); display:flex; flex-direction:column; overflow:hidden; }}
.sg-head {{ display:flex; align-items:center; gap:16px; padding:10px 28px; background:{T['panel']}; }}
.sg-bar {{ height:4px; flex-shrink:0; background:{BRAND_BAR}; }}
.sg-logo {{ height:44px; width:auto; display:block; }}
.sg-clock {{ font-size:26px; font-weight:700; color:{T['text']}; margin-left:8px; }}
.sg-chip .q-icon {{ font-size:24px; }}
.sg-chip b {{ font-weight:700; font-variant-numeric:tabular-nums; }}
.sg-chip.alert {{ border-color:#E5383B66; background:#E5383B0D; color:#D62F32; }}
.sg-title {{ font-size:32px; font-weight:700; color:{T['text']}; }}
.sg-body {{ flex:1; padding:20px 28px; gap:18px; display:flex; flex-direction:column; overflow:hidden; }}
.sg-panel {{ background:{T['panel']}; border:1px solid {T['line']}; border-radius:16px; }}
.sg-muted {{ color:{T['muted']}; }}
.mono {{ font-family:Consolas,'D2Coding',monospace; font-variant-numeric:tabular-nums; }}
.badge {{ display:inline-block; padding:4px 16px; border-radius:6px; font-weight:700; color:#fff; }}
.blink {{ animation:blink 1s steps(2,start) infinite; }}
@keyframes blink {{ 50% {{ background:rgba(229,56,59,.14); }} }}

/* 왼쪽 이동 메뉴: 왼쪽 끝 10px에 0.4초 머물면 열림. 어느 화면에서든 HOME_ZOOM 크기로 고정 */
.sg-nav-zone {{ position:fixed; left:0; top:0; width:10px; height:var(--sg-nav-h, 100vh); z-index:3000;
               zoom:var(--sg-nav-zoom, 1); }}
.sg-nav {{ position:fixed; left:0; top:0; width:330px; height:var(--sg-nav-h, 100vh); z-index:3001;
          zoom:var(--sg-nav-zoom, 1);
          display:flex; flex-direction:column; gap:4px; padding:22px 14px;
          background:{T['panel']}; border-right:1px solid {T['line']};
          box-shadow:4px 0 24px rgba(16,24,40,.12);
          transform:translateX(-105%); transition:transform .2s ease .15s; }}
.sg-nav-zone:hover + .sg-nav {{ transform:translateX(0); transition-delay:.4s; }}
.sg-nav:hover {{ transform:translateX(0); transition-delay:0s; }}
.sg-nav-logo {{ width:210px; margin:0 8px 20px; }}
.sg-nav-item {{ display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:10px;
               font-size:18px; font-weight:500; color:{T['text']}; text-decoration:none; }}
.sg-nav-item .q-icon {{ font-size:24px; color:{T['muted']}; }}
.sg-nav-item:hover {{ background:{T['bg']}; }}
.sg-nav-item.on {{ background:{B['blue']}14; color:{B['blue']}; font-weight:700; }}
.sg-nav-item.on .q-icon {{ color:{B['blue']}; }}

/* ===== v4 공통 규칙 (soft): 선 대신 그림자·여백, 둥근 모서리, 부드러운 전환 ===== */
:root {{ --sg-soft:#F6F7F9; --sg-ease:cubic-bezier(.2,.8,.2,1);
        --sg-shadow:0 1px 2px rgba(16,24,40,.04), 0 6px 20px rgba(16,24,40,.06);
        --sg-shadow-up:0 2px 4px rgba(16,24,40,.05), 0 16px 36px rgba(16,24,40,.10); }}
.sg-panel {{ border:none !important; border-radius:24px !important; box-shadow:var(--sg-shadow); }}
.sg-ico {{ color:{B['blue']}; }}

/* 얇은 둥근 스크롤바 */
::-webkit-scrollbar {{ width:12px; height:12px; }}
::-webkit-scrollbar-thumb {{ background:#D7DCE3; border-radius:999px; border:3px solid transparent;
                            background-clip:content-box; }}
::-webkit-scrollbar-thumb:hover {{ background:#BFC6D0; background-clip:content-box; }}
::-webkit-scrollbar-track {{ background:transparent; }}

/* 버튼·입력칸: 알약형, 테두리 옅게 */
.q-btn {{ border-radius:999px !important; letter-spacing:0;
         transition:transform .2s var(--sg-ease), filter .2s, background .2s; }}
.q-btn.q-btn--round {{ border-radius:50% !important; }}
.q-btn:not(.disabled):active {{ transform:scale(.97); }}
.q-btn--unelevated:not(.disabled):hover {{ filter:brightness(1.06); }}
.q-btn--outline:before {{ border:1.5px solid currentColor; opacity:.28; }}
.q-field--outlined .q-field__control {{ border-radius:14px !important; background:var(--sg-soft); }}
.q-field--outlined .q-field__control:before {{ border-color:transparent !important; }}

/* KPI 카드 */
.sg-kpi {{ flex:1; display:flex; align-items:center; gap:18px; padding:22px 28px; background:{T['panel']};
          border-radius:24px; box-shadow:var(--sg-shadow); cursor:pointer;
          transition:transform .25s var(--sg-ease), box-shadow .25s var(--sg-ease); }}
.sg-kpi:hover {{ transform:translateY(-2px); box-shadow:var(--sg-shadow-up); }}
.sg-kpi .sg-ico {{ display:inline-flex !important; align-items:center; justify-content:center;
                  width:60px; height:60px; border-radius:18px; background:{B['blue']}12; flex-shrink:0; }}
.sg-kpi .k-label {{ font-size:22px; font-weight:600; color:{T['text']}; }}
.sg-kpi .k-value {{ margin-left:auto; font-size:54px; font-weight:650; letter-spacing:-0.02em;
                   color:{T['text']}; font-variant-numeric:tabular-nums; }}
.sg-kpi.alert .k-value {{ color:#E5383B; }}
.sg-kpi.alert .sg-ico {{ background:#E5383B14; color:#E5383B; }}
.sg-kpi.on {{ box-shadow:0 0 0 3px {B['blue']}40, var(--sg-shadow-up); }}

/* 위험 등급 배지: 알약형, 테두리 없음. 재난만 채움 */
.sg-grade {{ display:inline-flex; align-items:center; padding:5px 16px; border-radius:999px;
            font-size:19px; font-weight:650; white-space:nowrap;
            color:var(--c); background:color-mix(in srgb, var(--c) 11%, #fff); }}
.sg-grade.solid {{ color:#fff; background:var(--c); }}

/* 상태 점 + 글자 */
.sg-dot {{ display:inline-flex; align-items:center; gap:10px; font-size:20px; font-weight:600; color:var(--c); }}
.sg-dot::before {{ content:''; width:12px; height:12px; border-radius:50%; background:var(--c); flex-shrink:0;
                  box-shadow:0 0 0 4px color-mix(in srgb, var(--c) 16%, transparent); }}

/* 처리 단계 미니 진행선 */
.sg-step {{ display:flex; gap:5px; }}
.sg-step i {{ width:30px; height:8px; border-radius:999px; background:#E6E9EE; }}
.sg-step i.on {{ background:var(--c, {B['blue']}); }}

/* 필터 탭 */
.sg-tabs {{ display:inline-flex; gap:4px; padding:5px; border-radius:999px; background:#ECEFF3; }}
.sg-tab {{ padding:9px 22px; border-radius:999px; font-size:20px; font-weight:500; color:{T['muted']};
          cursor:pointer; white-space:nowrap; transition:all .2s var(--sg-ease); }}
.sg-tab b {{ margin-left:8px; font-weight:600; }}
.sg-tab.on {{ background:{T['panel']}; color:{T['text']}; font-weight:650; box-shadow:0 2px 8px rgba(16,24,40,.08); }}

/* 제목줄 상태 칩 */
.sg-chip {{ display:inline-flex; align-items:center; gap:8px; padding:8px 18px; border-radius:999px;
           background:var(--sg-soft); font-size:20px; white-space:nowrap; }}

/* 표 (soft) */
.sg-table {{ width:100%; border-collapse:separate; border-spacing:0 4px; }}
.sg-table th {{ text-align:left; padding:10px 18px; font-size:17px; font-weight:500; color:{T['muted']}; }}
.sg-table td {{ padding:14px 18px; font-size:20px; background:transparent; }}
.sg-sub {{ display:block; font-size:16px; color:{T['muted']}; margin-top:2px; }}

/* 알림 창 (모든 화면 공통) */
.q-notification {{ font-size:24px !important; padding:18px 36px !important; border-radius:20px !important; }}
.q-notification__icon {{ font-size:36px !important; }}
.q-notification__message {{ padding:6px 0 !important; font-weight:650; }}

</style>
"""


def apply_style():
    ui.add_head_html(STYLE)


def fit_zoom(fixed=None):
    """화면 배율. fixed가 없으면 창 폭 / DESIGN_WIDTH로 자동, 있으면 그 배율로 고정.
    이동 메뉴는 어느 화면에서든 HOME_ZOOM 크기로 보이도록 따로 보정."""
    z = 'null' if fixed is None else fixed
    ui.add_head_html(f"""
<script>
(() => {{
  const fit = () => {{
    const z = {z} ?? window.innerWidth / {config.DESIGN_WIDTH};
    const r = document.documentElement;
    r.style.zoom = z;
    r.style.setProperty('--sg-h', Math.floor(window.innerHeight / z) + 'px');
    r.style.setProperty('--sg-nav-zoom', {config.HOME_ZOOM} / z);
    r.style.setProperty('--sg-unzoom', 1 / z);
    r.style.setProperty('--sg-nav-h', Math.floor(window.innerHeight / {config.HOME_ZOOM}) + 'px');
  }};
  fit();
  window.addEventListener('resize', fit);
}})();
</script>
""")


def side_nav(current):
    """왼쪽 이동 메뉴. 페이지마다 1번 호출. current: 'home' 또는 화면 번호"""
    ui.element('div').classes('sg-nav-zone')
    with ui.element('div').classes('sg-nav'):
        ui.html('<img src="/assets/logo_full.png" class="sg-nav-logo">')
        items = [('home', '/', 'home', '메인')]
        items += [(n, f'/screen/{n}', ICONS[n], config.SCREEN_NAMES[n])
                  for n in range(1, 7)]
        for key, url, icon, label in items:
            cls = 'sg-nav-item' + (' on' if key == current else '')
            with ui.element('a').props(f'href={url}').classes(cls):
                ui.icon(icon)
                ui.label(label)
        ui.space()
        with ui.element('a').props('href=/logout').classes('sg-nav-item'):   # 모든 페이지에 로그아웃
            ui.icon('logout')
            ui.label('로그아웃')


def screen_root():
    """화면1~6 공통 틀. 창 폭에 맞춰 자동 확대·축소"""
    fit_zoom()
    return ui.element('div').classes('sg-screen')


def header(title, left=None):
    """상단 제목줄 + 3색 띠. left: 제목 옆에 넣을 내용(함수). 오른쪽 영역을 돌려줌."""
    with ui.element('div').classes('sg-head'):
        with ui.element('a').props('href=/'):
            ui.html('<img src="/assets/logo.png" class="sg-logo">')
        ui.label(title).classes('sg-title')
        if left:
            left()
        ui.space()
        right = ui.row().classes('items-center gap-6 no-wrap')
    ui.element('div').classes('sg-bar')
    return right

def chip(icon, label, value=None, alert=False, color=None):
    """제목줄 오른쪽 상태 칩. alert=True면 연한 빨강. color는 아이콘 색"""
    with ui.element('div').classes('sg-chip' + (' alert' if alert else '')):
        ui.icon(icon).style(f'color:{color or (C_RED if alert else B["blue"])}')
        ui.label(label)
        if value is not None:
            ui.html(f'<b>{value}</b>')


def clock():
    """제목줄 시계. 1초마다 갱신 (서버 상태와 무관)"""
    lb = ui.label().classes('sg-clock mono')
    tick = lambda: lb.set_text(time.strftime('%Y.%m.%d %H:%M:%S'))
    tick()
    ui.timer(1.0, tick)
    return lb


def badge(text, color, size=22):
    ui.html(f'<span class="badge" style="background:{color};font-size:{size}px">{text}</span>')

def grade_html(grade):
    """위험 등급 배지 HTML. 표 안에 넣을 때 사용"""
    base, text = GRADE_STYLE.get(grade, ('#6B7280', '#6B7280'))
    if grade in SOLID_GRADES:
        return f'<span class="sg-grade solid" style="--c:{base}">{grade}</span>'
    return f'<span class="sg-grade" style="--c:{text}">{grade}</span>'


def grade(grade_name):
    ui.html(grade_html(grade_name))


def dot_html(status, text=None):
    """상태 점 + 글자 HTML. text를 주면 글자만 바꿔 표시(색은 status 기준)"""
    c = STATUS_COLOR.get(status, '#6B7280')
    return f'<span class="sg-dot" style="--c:{c}">{text or status}</span>'


def dot(status, text=None):
    ui.html(dot_html(status, text))


def step_html(stage):
    """처리 단계 미니 진행선 5칸. 현재 단계까지 채움. 조치 완료 이후는 초록"""
    stages = config.STAGES
    n = stages.index(stage) + 1 if stage in stages else 0
    done = stage in (config.ACTION_DONE_STAGE, config.DONE_STAGE)
    c = '#2EA043' if done else B['blue']
    cells = ''.join(f'<i class="{"on" if i < n else ""}"></i>' for i in range(len(stages)))
    return f'<span class="sg-step" style="--c:{c}" title="{stage}">{cells}</span>'


def step(stage):
    ui.html(step_html(stage))


def kpi(label, value, icon=None, alert=False, active=False, on_click=None):
    """KPI 카드. alert=True면 빨강 세로선·숫자, active=True면 선택 테두리"""
    cls = 'sg-kpi' + (' alert' if alert else '') + (' on' if active else '')
    card = ui.element('div').classes(cls)
    if on_click:
        card.on('click', on_click)
    with card:
        if icon:
            ui.icon(icon).classes('sg-ico').style('font-size:30px')
        ui.label(label).classes('k-label')
        ui.label(str(value)).classes('k-value')
    return card


def tabs(items, current, on_change):
    """필터 탭. items: [(키, 라벨, 개수)], current: 선택 키, on_change(키)"""
    with ui.element('div').classes('sg-tabs'):
        for key, label, count in items:
            t = ui.html(f'{label}<b>{count}</b>').classes('sg-tab' + (' on' if key == current else ''))
            t.on('click', lambda _, k=key: on_change(k))

def live(build, every=None):
    """공유 상태가 바뀌면 build() 영역을 다시 그림. every(초) 간격 갱신도 가능."""
    @ui.refreshable
    def area():
        build()

    area()
    seen = {'v': S.state.version, 't': time.time()}

    def check():
        if S.state.version != seen['v'] or (every and time.time() - seen['t'] >= every):
            seen['v'], seen['t'] = S.state.version, time.time()
            area.refresh()

    ui.timer(0.5, check)
    return area