"""화면4 · 대응인력 현황 (v10, 슬랙형)
왼쪽 목록: 대응 중 · 부재 있음 · 사업단별 사업장 · 공단 본부 (상태 점 + 배지)
가운데: 선택 사업장 — 호출 순서 · 처리 경과 · 사업장 인력 / 이번 주 근무표
오른쪽: 인력 프로필 (상태 변경 · 근무표 · 호출 순서 · 오늘 기록)
화면1에서 상황을 고르면 해당 사업장이 자동 선택됨. 내부 보고·신고·유관기관 연락은 화면1에서 처리
근거: 긴급상황 대응 매뉴얼 · scenario.xlsx 인력 부재 시트"""
import time
from datetime import datetime, timedelta

from nicegui import ui

import config
import state as S
from screens import screen_root, header, live, clock, grade_html, T, C, B

GRAY = C['unknown']
YEL = '#8A6400'
ROLE_NAME = {'팀장': '소관 팀장'}
ROLE_COLOR = {'현장 담당자': B['sky'], '안전요원': '#0E8F80', '소방안전관리자': '#D0583E',
              '현장 책임자': B['blue'], '팀장': '#7C5CC4', '재난안전상황실': '#C62828', '경영진': '#374151'}
ROLE_SORT = list(config.ESCALATION) + ['팀장', '재난안전상황실', '경영진']
STATE_STYLE = {   # 인력 상태: (점·바탕 색, 글자색) — 위에서부터 시급한 순
    '미응답': (C['alarm'], '#C62828'), '응답 대기': ('#E9B200', YEL), '출동 중': (B['blue'], '#1F5F95'),
    '보고 받음': (B['sky'], '#1F5F95'), '부재': (C['warn'], '#A85400'), '근무 중': (C['ok'], '#1E7A34')}
STATE_ORDER = list(STATE_STYLE)
NO_ONE = ('호출 대상 없음', '전원 미응답')
TABS = ['인력', '이번 주 근무표']
KEY_TEXT = {'재난': '#7A0916', '긴급': '#C62828', '주의': '#A85400', '알림': '#7A5F00'}
DAYS = ['월', '화', '수', '목', '금', '토', '일']
DAY_STYLE = {   # 근무표 칸: (바탕, 글자색)
    '근무': ('#D7EFDD', '#1E7A34'), '휴무': ('#F1F3F6', '#8A94A3'), '연차': ('#FFE1BF', '#A85400'),
    '교육': ('#D9E8FB', '#1F5F95'), '출장': ('#E7DFFA', '#5B3FA8'), '병가': ('#FDDCDC', '#C62828'),
    '기타': ('#E8EBEF', '#4B5563')}
LOG_SKIP = ('체크 ', '체크 해제')          # 처리 경과에서 뺄 기록 (체크리스트는 화면1)
TAG = {   # 핵심 꼬리표 (유형명 → 표시). 화면3도 사용
    '화재': '화재', '전기차 충전·주차구역 화재': '전기차 화재', '정전': '정전', '가스 누설': '가스',
    '시설 침수': '침수', '붕괴': '붕괴', '흉기 난동': '흉기', '싸움·폭행': '폭행', '미아 발생': '미아',
    '이상동기(다수가 흩어지거나 달아남)': '이상동기', '음주·난폭운전 의심': '난폭운전', '불법촬영·성추행': '불법촬영',
    '수영장 익수 위험': '익수', '응급환자': '응급환자', '온열질환': '온열질환', '요보호자 발견': '요보호자',
    '기타 안전사고(넘어짐·부딪힘·끼임 등)': '안전사고', '차량·보행자 충돌': '차량 사고',
    '다중운집 인파사고': '인파', '지진': '지진', '지진해일 특보': '지진해일', '감염병': '감염병',
    '폭발물·의심물건 발견': '테러', '의심 우편물': '테러', '생물테러 의심물체': '테러', '화학 테러': '테러',
    '방사능 테러': '테러', '폭파 협박': '테러', '인질극': '테러', '시설물 낙하·전도': '시설물 전도',
}

CSS = f"""
<style>
/* 제목줄 */
.s4-cnt {{ display:inline-flex; align-items:center; gap:10px; margin-left:18px; }}
.s4-cnt > div {{ display:flex; align-items:center; gap:10px; padding:8px 20px; border-radius:999px; font-size:21px;
                font-weight:650; color:#374151; background:#ECEFF3; }}
.s4-cnt > div b {{ font-size:24px; font-weight:800; font-variant-numeric:tabular-nums; }}
.s4-cnt > div.red {{ background:#FDECEC; color:#C62828; }}
.s4-cnt > div.yel {{ background:#FFF6D6; color:{YEL}; }}
.s4-cnt > div.org {{ background:#FFF1E0; color:#A85400; }}
.s4-mode {{ display:inline-flex; gap:4px; padding:5px; border-radius:999px; background:#ECEFF3; }}
.s4-mode > div {{ display:flex; align-items:center; gap:8px; padding:8px 20px; border-radius:999px; font-size:20px;
                 font-weight:650; color:#4B5563; cursor:pointer; }}
.s4-mode > div .q-icon {{ font-size:22px; }}
.s4-mode > div.on {{ background:#1F2937; color:#fff; }}
.s4-mode-s {{ font-size:17px; color:{T['muted']}; margin:0 12px; white-space:nowrap; cursor:pointer; }}

/* 3단 배치 */
.s4-app {{ flex:1; min-height:0; display:grid; grid-template-columns:520px minmax(0,1fr) 660px; gap:20px; }}
.s4-col {{ min-height:0; display:flex; flex-direction:column; overflow:hidden; }}

/* 왼쪽 목록 (채널 목록) */
.s4-nav {{ background:#1F2A37; color:#E5E9EF; border-radius:24px; padding:20px 14px; }}
.s4-nav .q-field__control {{ height:60px; min-height:60px; padding:0 14px; background:#FFFFFF !important;
                            border-radius:16px !important; box-shadow:0 0 0 2px #FFFFFF33; }}
.s4-nav .q-field__control:before, .s4-nav .q-field__control:after {{ display:none !important; }}
.s4-nav .q-field--focused .q-field__control {{ box-shadow:0 0 0 3px {B['blue']}99; }}
.s4-nav .q-field__native, .s4-nav .q-field__marginal {{ height:60px; min-height:60px; }}
.s4-nav .q-field__native {{ padding:0 0 0 6px; color:#1F2937 !important; font-size:22px !important; font-weight:600; }}
.s4-nav .q-field__native::placeholder {{ color:#6B7280; opacity:1; }}
.s4-nav .q-field__prepend .q-icon, .s4-nav .q-field__append .q-icon {{ color:#4B5563 !important; font-size:26px !important; }}
.s4-navs {{ flex:1; min-height:0; overflow-y:auto; margin-top:16px; padding-right:4px; }}
.s4-sh {{ display:flex; align-items:center; gap:8px; margin-top:14px; padding:16px 10px 10px; border-top:1px solid #36424F;
         font-size:19px; font-weight:800; letter-spacing:.02em; color:#93A0B1; cursor:pointer; user-select:none; }}
.s4-navs > .s4-sh:first-child {{ margin-top:0; border-top:none; padding-top:4px; }}
.s4-sh .q-icon {{ font-size:22px; }}
.s4-sh b {{ margin-left:auto; padding:1px 10px; border-radius:999px; background:#2B3746; font-size:17px; font-weight:800; color:#C8D0DB; }}
.s4-ch {{ display:flex; align-items:center; gap:12px; padding:7px 12px; border-radius:12px; cursor:pointer; min-width:0; }}
.s4-ch:hover {{ background:#2B3746; }}
.s4-ch.on {{ background:{B['blue']}; }}
.s4-ch .dt {{ width:12px; height:12px; border-radius:50%; flex-shrink:0; background:var(--c); }}
.s4-ch .nm {{ font-size:22px; font-weight:600; color:#C3CBD6; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s4-ch.on .nm {{ color:#fff; }}
.s4-ch .tg {{ margin-left:auto; font-size:16px; font-weight:700; color:#93A0B1; white-space:nowrap; }}
.s4-ch .bd {{ margin-left:auto; min-width:32px; height:32px; padding:0 9px; border-radius:999px; display:flex; align-items:center;
             justify-content:center; font-size:18px; font-weight:800; color:#fff; background:var(--c); flex-shrink:0; }}
.s4-ch .tg + .bd {{ margin-left:8px; }}
/* 대응 중: 두 줄 카드 + 왼쪽 색 막대 */
.s4-ch.big {{ padding:12px 14px 12px 20px; margin-bottom:8px; background:#273445; border-radius:14px;
             box-shadow:inset 6px 0 0 var(--c); }}
.s4-ch.big:hover {{ background:#2F3E52; }}
.s4-ch.big.on {{ background:{B['blue']}; box-shadow:inset 6px 0 0 #fff; }}
.s4-ch.big .nm {{ font-size:25px; font-weight:800; color:#fff; }}
.s4-ch .sub {{ font-size:18px; font-weight:600; color:#AEB8C6; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s4-ch .sub.red {{ color:#FF9B9B; font-weight:800; }}
.s4-ch.on .sub {{ color:#E8F1FB; }}

/* 가운데 (채널 화면) */
.s4-main {{ padding:26px 32px 20px; gap:18px; }}
.s4-mh {{ display:flex; align-items:center; gap:16px; flex-wrap:wrap; flex-shrink:0; }}
.s4-mh .nm {{ font-size:38px; font-weight:800; letter-spacing:-0.02em; }}
.s4-mh .sub {{ font-size:21px; color:#4B5563; }}
.s4-ic {{ display:inline-flex; align-items:center; gap:8px; padding:8px 18px; border-radius:999px; font-size:21px; font-weight:800;
         color:var(--t); background:color-mix(in srgb, var(--c) 14%, #fff); cursor:pointer; }}
.s4-ic.on {{ box-shadow:inset 0 0 0 2.5px var(--c); }}
.s4-tabs {{ display:flex; gap:28px; border-bottom:2px solid #E8EBEF; flex-shrink:0; }}
.s4-tabs > div {{ padding:10px 2px 12px; font-size:23px; font-weight:650; color:#6B7280; cursor:pointer; margin-bottom:-2px; }}
.s4-tabs > div.on {{ color:{T['text']}; font-weight:800; box-shadow:inset 0 -3px 0 {B['blue']}; }}
.s4-mbody {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:26px; padding-right:6px; }}
.s4-st {{ display:flex; align-items:center; gap:10px; font-size:24px; font-weight:800; }}
.s4-st .q-icon {{ font-size:28px; color:{B['blue']}; }}
.s4-st .r {{ margin-left:auto; font-size:19px; font-weight:500; color:#4B5563; }}
.s4-calm {{ display:flex; align-items:center; gap:12px; padding:20px 24px; border-radius:18px; background:#EEF8F0;
           font-size:23px; font-weight:700; color:#1E7A34; }}
.s4-calm .q-icon {{ font-size:30px; }}

/* 호출 순서 */
.s4-call {{ display:grid; grid-template-columns:44px 64px minmax(0,1fr) auto auto; align-items:center; gap:16px;
           padding:14px 20px; border-radius:18px; background:var(--sg-soft); }}
.s4-call.now {{ background:#fff; box-shadow:inset 0 0 0 3px var(--c); }}
.s4-call.skip {{ background:#FFF5E8; }}
.s4-call .no {{ width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center;
               font-size:21px; font-weight:800; color:#fff; background:var(--c); }}
.s4-call .nm {{ font-size:27px; font-weight:800; }}
.s4-call.skip .nm {{ text-decoration:line-through; text-decoration-color:#C2410C80; }}
.s4-call .rl {{ font-size:20px; color:#4B5563; }}
.s4-call .st {{ font-size:23px; font-weight:800; color:var(--t); white-space:nowrap; text-align:right; }}
.s4-btn {{ padding:10px 26px; border-radius:999px; font-size:21px; font-weight:800; cursor:pointer; white-space:nowrap;
          color:#fff; background:var(--c); }}
.s4-btn:hover {{ filter:brightness(1.08); }}
.s4-btn.ghost {{ color:var(--c); background:#fff; box-shadow:inset 0 0 0 2px var(--c); }}
.s4-none {{ display:flex; align-items:center; gap:14px; padding:16px 20px; border-radius:18px; background:#FDE8E8;
           font-size:23px; font-weight:800; color:#B42318; }}
.s4-none .q-icon {{ font-size:28px; }}

/* 처리 경과 */
.s4-log {{ display:flex; flex-direction:column; gap:2px; }}
.s4-lg {{ display:grid; grid-template-columns:90px minmax(0,1fr); gap:16px; padding:8px 6px; font-size:21px; }}
.s4-lg .t {{ font-weight:700; color:#4B5563; font-variant-numeric:tabular-nums; }}
.s4-lg.memo .x {{ font-weight:700; color:#1F5F95; }}

/* 인력 행 (멤버 목록) */
.s4-mem {{ display:grid; grid-template-columns:64px minmax(0,1fr) auto 230px; align-items:center; gap:18px;
          padding:12px 18px; border-radius:18px; cursor:pointer; }}
.s4-mem:hover {{ background:var(--sg-soft); }}
.s4-mem.on {{ background:{B['blue']}12; }}
.s4-mem .nm {{ font-size:26px; font-weight:800; }}
.s4-mem .rl {{ font-size:20px; color:#4B5563; }}
.s4-mem .ds {{ font-size:18px; color:#4B5563; text-align:right; margin-top:4px; }}
.s4-mem .ds.alt {{ color:#1F5F95; font-weight:700; }}
.s4-mem .ph {{ font-size:21px; font-weight:600; color:#1F2937; font-variant-numeric:tabular-nums; text-align:right; }}
.s4-av {{ position:relative; width:58px; height:58px; border-radius:50%; flex-shrink:0; display:flex; align-items:center;
         justify-content:center; font-size:25px; font-weight:800; color:#fff; background:var(--r); }}
.s4-av i {{ position:absolute; right:-2px; bottom:-2px; width:20px; height:20px; border-radius:50%; background:var(--d); border:3px solid #fff; }}
.s4-av.lg {{ width:110px; height:110px; font-size:44px; }}
.s4-av.lg i {{ width:28px; height:28px; border-width:4px; }}
.s4-pill {{ display:inline-flex; align-items:center; gap:8px; padding:7px 18px; border-radius:999px; font-size:21px;
           font-weight:800; white-space:nowrap; color:var(--t); background:color-mix(in srgb, var(--c) 14%, #fff); }}
.s4-pill::before {{ content:''; width:12px; height:12px; border-radius:50%; background:var(--c); }}

/* 이번 주 근무표 */
.s4-wk {{ display:grid; grid-template-columns:minmax(260px,1.2fr) repeat(7, minmax(86px,1fr)); gap:10px; align-items:center;
         padding:10px 14px; border-radius:16px; }}
.s4-wk.head {{ font-size:20px; font-weight:700; color:#4B5563; }}
.s4-wk.head .day {{ text-align:center; font-size:23px; font-weight:800; color:#1F2937; padding:6px 0; line-height:1.2; }}
.s4-wk.head .day small {{ display:block; font-size:16px; font-weight:600; color:#6B7280; }}
.s4-wk.head .day.today {{ color:#fff; background:{B['blue']}; border-radius:14px; }}
.s4-wk.head .day.today small {{ color:#fff; }}
.s4-wk .who {{ font-size:24px; font-weight:800; }}
.s4-wk .who small {{ display:block; font-size:18px; font-weight:500; color:#4B5563; }}
.s4-day {{ height:58px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:20px;
          font-weight:750; background:var(--b); color:var(--t); }}
.s4-day.today {{ box-shadow:0 0 0 3px {B['blue']}; font-weight:850; }}
.s4-wlegend {{ display:flex; gap:18px; font-size:19px; font-weight:600; color:#374151; }}
.s4-wlegend span {{ display:inline-flex; align-items:center; gap:8px; }}
.s4-wlegend i {{ width:28px; height:20px; border-radius:6px; }}

/* 오른쪽 프로필 */
.s4-prof {{ padding:28px 28px 20px; }}
.s4-pbody {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:24px; padding-right:4px; }}
.s4-ph {{ display:flex; align-items:center; gap:22px; }}
.s4-ph .nm {{ font-size:38px; font-weight:800; letter-spacing:-0.02em; }}
.s4-ph .rl {{ font-size:21px; color:#374151; margin-top:4px; }}
.s4-ph .tel {{ font-size:22px; color:#1F2937; font-weight:600; margin-top:2px; font-variant-numeric:tabular-nums; }}
.s4-empty {{ margin:auto; text-align:center; font-size:23px; color:#6B7280; line-height:1.7; }}
.s4-empty .q-icon {{ font-size:56px; color:#C5CCD5; }}
.s4-opts {{ display:flex; flex-wrap:wrap; gap:10px; }}
.s4-opt {{ padding:10px 24px; border-radius:999px; background:var(--sg-soft); font-size:21px; font-weight:700; color:#4B5563; cursor:pointer; }}
.s4-opt:hover {{ background:#E9ECF0; }}
.s4-opt.on {{ background:var(--c); color:#fff; }}
.s4-note {{ padding:14px 18px; border-radius:16px; font-size:21px; font-weight:700; color:#1F5F95; background:{B['blue']}10; }}
.s4-week {{ display:grid; grid-template-columns:repeat(7, 1fr); gap:8px; }}
.s4-week > div {{ text-align:center; font-size:19px; font-weight:700; color:#374151; }}
.s4-week .s4-day {{ margin-top:6px; height:52px; font-size:18px; }}
.s4-kv {{ display:flex; align-items:center; padding:12px 16px; border-radius:14px; background:var(--sg-soft); font-size:21px; }}
.s4-kv b {{ margin-left:auto; color:{B['blue']}; }}
.s4-rec {{ display:grid; grid-template-columns:150px minmax(0,1fr); gap:12px; padding:10px 6px; font-size:20px; cursor:pointer; border-radius:12px; }}
.s4-rec:hover {{ background:var(--sg-soft); }}
.s4-rec .t {{ color:#4B5563; font-variant-numeric:tabular-nums; }}
</style>
"""


# ── 표시 도우미 ──
def short_tag(inc):
    """핵심 꼬리표 한 단어 (화면3도 사용)"""
    return TAG.get(inc['type']) or inc['type'].split('(')[0].strip()[:8].strip()


def rname(role):
    return ROLE_NAME.get(role or '', role or '')


def mmss(sec):
    sec = max(0, int(sec))
    return f'{sec // 60}:{sec % 60:02d}'


def pill_html(st, text=None):
    c, t = STATE_STYLE[st]
    return f'<span class="s4-pill" style="--c:{c};--t:{t}">{text or st}</span>'


def day_html(code, today=False):
    b, t = DAY_STYLE.get(code, DAY_STYLE['기타'])
    return f'<div class="s4-day{" today" if today else ""}" style="--b:{b};--t:{t}">{code}</div>'


def disp_name(p):
    return p['name'] if p['site'] else (p.get('title') or p['role'])


def today_idx():
    return time.localtime(S.now()).tm_wday


def week_start():
    return datetime.fromtimestamp(S.now()).date() - timedelta(days=today_idx())


def by_urgency(incs):
    return sorted(incs, key=lambda i: (S.GRADE_RANK[i['grade']], i['start']))


# ── 상황 계산 ──
def next_action(inc):
    """다음 연락 (종류, 역할, 시각). 호출 순서에서 부재가 아니고 아직 부르지 않은 첫 인력이 다음 호출 대상"""
    order = S.order_of(inc)
    sts = {r: S.call_status(inc, r) for r in order}
    for r in reversed(order):
        if sts[r][0] == '응답':
            return '출동 중', r, sts[r][1]
    for r in reversed(order):
        if sts[r][0] == '호출 중':
            return '응답 대기', r, sts[r][1]
    missed = False
    for r in order:
        st = sts[r][0]
        if st == '미응답':
            missed = True
        elif st == '미호출' and not S.is_absent(inc, r):
            return ('차순위 호출' if missed else '호출 전'), r, None
    return ('전원 미응답' if missed else '호출 대상 없음'), None, None


def needs_action(inc):
    """관제사가 지금 움직여야 하는 상황: 미응답 · 호출 가능 인력 없음"""
    return next_action(inc)[0] in NO_ONE or any(S.call_status(inc, r)[0] == '미응답' for r in S.order_of(inc))


# ── 인력 계산 ──
def person_state(p):
    """인력 상태 (상태, 설명, 상황) — 미조치 상황 중 가장 시급한 것 기준"""
    if not p.get('present', True):
        return '부재', f"{p.get('absence') or '부재'} · 호출 제외", None
    found = []
    for inc in (S.open_incidents(p['site']) if p['site'] else S.open_incidents()):
        st, ts = S.call_status(inc, p['role'])
        key = {'미응답': '미응답', '호출 중': '응답 대기', '응답': '출동 중', '통보 완료': '보고 받음'}.get(st)
        if not key:
            continue
        desc = {'미응답': f'{mmss(S.now() - ts)} 미응답', '응답 대기': f'{mmss(S.now() - ts)} 경과',
                '출동 중': f'{S.hm(ts)} 응답', '보고 받음': f'{S.hm(ts)} 보고'}[key]
        site = S.state.sites[inc['site']]['name']
        found.append((STATE_ORDER.index(key), key, f'{site} {short_tag(inc)} · {desc}', inc))
    if found:
        _, key, desc, inc = min(found, key=lambda x: x[0])
        return key, desc, inc
    return '근무 중', '', None


def substitute(p):
    """부재 인력 대신 대응할 같은 사업장 현장 인력"""
    if not p['site'] or p['role'] not in config.ESCALATION:
        return None
    for r in list(config.FIELD_ORDER_DEFAULT) + list(config.ESCALATION):
        if r == p['role']:
            continue
        q = S.staff_of(p['site'], r)
        if q and q.get('present', True):
            return q
    return None


def call_records(p):
    out = []
    for inc in S.state.incidents:
        if p['site'] and inc['site'] != p['site']:
            continue
        for n in inc['notices']:
            if n['target'] == p['role']:
                out.append((inc, n))
    return sorted(out, key=lambda x: -x[1]['ts'])


def site_people(sid):
    return [q for q in (S.staff_of(sid, r) for r in ROLE_SORT) if q]


def avatar_html(p, size=''):
    st = person_state(p)[0]
    return (f'<div class="s4-av {size}" style="--r:{ROLE_COLOR.get(p["role"], GRAY)};'
            f'--d:{STATE_STYLE[st][0]}">{disp_name(p)[:1]}<i></i></div>')


def site_flag(sid):
    """왼쪽 목록 점 색 · 꼬리표: 미응답·인력 없음 = 빨강 / 상황 = 등급색 / 부재 = 주황 / 정상 = 초록"""
    incs = by_urgency(S.open_incidents(sid))
    if incs:
        if any(needs_action(i) for i in incs):
            return C['alarm'], short_tag(incs[0]), True
        return S.GRADE_COLOR[incs[0]['grade']], short_tag(incs[0]), True
    away = [p for p in site_people(sid) if not p.get('present', True)]
    if away:
        return C['warn'], ' · '.join(sorted({p.get('absence') or '부재' for p in away})), False
    return C['ok'], '', False


def draw():
    ui.add_head_html(CSS)
    view = {'site': None, 'inc': None, 'pid': None, 'tab': TABS[0], 'q': '',
            'open': set(), 'last_sel': None}
    refs = {}

    # ── 선택 ──
    def urgent_sites():
        out = []
        for inc in by_urgency(S.open_incidents()):
            if inc['site'] not in out:
                out.append(inc['site'])
        return sorted(out, key=lambda sid: not any(needs_action(i) for i in S.open_incidents(sid)))

    def cur_site():
        if view['site'] in S.state.sites:
            return view['site']
        u = urgent_sites()
        return u[0] if u else sorted(S.state.sites)[0]

    def refresh_all():
        for k in ('side', 'main', 'prof'):
            if k in refs:
                refs[k].refresh()

    def pick_site(sid):
        view['site'], view['inc'], view['pid'], view['tab'] = sid, None, None, TABS[0]
        refresh_all()

    def pick_person(pid):
        view['pid'] = pid
        refs['prof'].refresh()
        refs['main'].refresh()

    def sync():
        """화면1 선택 → 해당 사업장 자동 선택 (같은 상황을 다시 눌러도 이동)"""
        seq = getattr(S.state, 'select_seq', 0)
        if seq == view['last_sel']:
            return
        view['last_sel'] = seq
        sel = S.state.selected_incident
        inc = S.get_incident(sel) if sel else None
        if inc and not S.is_closed(inc):
            view['site'], view['inc'], view['pid'], view['tab'] = inc['site'], inc['id'], None, TABS[0]
            refresh_all()

    from nicegui import Client
    client = ui.context.client

    def push():
        if client.id not in Client.instances:
            S.off_select(push)
            return
        with client:
            sync()

    S.on_select(push)

    # ── 제목줄 ──
    def build_counts():
        n = {'미응답': 0, '호출 중': 0}
        for inc in S.open_incidents():
            for r in S.order_of(inc):
                st = S.call_status(inc, r)[0]
                if st in n:
                    n[st] += 1
        absent = sum(1 for p in S.state.staff if not p.get('present', True))
        with ui.element('div').classes('s4-cnt'):
            for label, v, cls in [('미응답', n['미응답'], 'red'), ('응답 대기', n['호출 중'], 'yel'), ('오늘 부재', absent, 'org')]:
                ui.html(f'<div class="{cls if v else ""}">{label} <b>{v}</b></div>')

    def build_modes():
        with ui.row().classes('items-center no-wrap gap-0'):
            with ui.element('div').classes('s4-mode'):
                for mode, icon in [('주간', 'light_mode'), ('야간·공휴일', 'dark_mode')]:
                    seg = ui.element('div').classes('on' if S.shift() == mode else '')
                    seg.on('click', lambda e, m=mode: S.set_shift(m))
                    with seg:
                        ui.icon(icon)
                        ui.label(mode)
            if S.state.shift_override is None:
                ui.label('시각 기준 자동').classes('s4-mode-s')
            else:
                ui.label('수동 전환 · 자동으로').classes('s4-mode-s').on('click', lambda e: S.set_shift(None))

    # ── 왼쪽 목록 ──
    def ch_row(sid, badge=None, big=False):
        """왼쪽 목록 한 줄. big = 대응 중 사업장 (두 줄 카드: 유형 · 등급 · 경과 · 조치 필요)"""
        c, tag, hot = site_flag(sid)
        cls = 's4-ch' + (' big' if big else '') + (' on' if sid == cur_site() else '')
        row = ui.element('div').classes(cls).style(f'--c:{c}')
        row.on('click', lambda e, x=sid: pick_site(x))
        with row:
            if not big:
                ui.element('span').classes('dt')
            with ui.element('div').style('flex:1;min-width:0'):
                ui.label(S.state.sites[sid]['name']).classes('nm')
                if big:
                    incs = by_urgency(S.open_incidents(sid))
                    top = incs[0]
                    warn = ''
                    if any(S.call_status(i, r)[0] == '미응답' for i in incs for r in S.order_of(i)):
                        warn = '미응답'
                    elif any(next_action(i)[0] in NO_ONE for i in incs):
                        warn = '호출 가능 인력 없음'
                    ui.label(' · '.join(x for x in [short_tag(top), top['grade'], S.ago(top['start']), warn] if x)) \
                        .classes('sub' + (' red' if warn else ''))
            if tag and not big:
                ui.label(tag).classes('tg')
            if badge and badge > 1:
                ui.label(str(badge)).classes('bd')

    def sec_head(key, icon, label, n, fold=True):
        h = ui.element('div').classes('s4-sh')
        if fold:
            h.on('click', lambda e, k=key: toggle(k))
        with h:
            ui.icon(icon if not fold else ('expand_more' if key in view['open'] else 'chevron_right'))
            ui.label(label)
            ui.html(f'<b>{n}</b>')

    def toggle(key):
        view['open'] ^= {key}
        refs['side'].refresh()

    def build_side():
        q = view['q'].strip()
        with ui.element('div').classes('s4-navs'):
            if q:
                hits = [s['id'] for s in sorted(S.state.sites.values(), key=lambda s: s['name'])
                        if q in s['name'] or q in s['dept']
                        or any(q in p['name'] or q in rname(p['role']) for p in site_people(s['id']))]
                sec_head('', 'search', '검색 결과', len(hits), fold=False)
                for sid in hits:
                    ch_row(sid)
                return
            urgent = urgent_sites()
            sec_head('', 'emergency', '대응 중', len(urgent), fold=False)
            for sid in urgent:
                ch_row(sid, len(S.open_incidents(sid)), big=True)
            away = [sid for sid in sorted(S.state.sites, key=lambda x: S.state.sites[x]['name'])
                    if sid not in urgent and any(not p.get('present', True) for p in site_people(sid))]
            sec_head('', 'event_busy', '부재 있음', len(away), fold=False)
            for sid in away:
                ch_row(sid)
            for dept in config.DEPTS:
                sids = [s['id'] for s in sorted(S.state.sites.values(), key=lambda s: s['name']) if s['dept'] == dept]
                if not sids:
                    continue
                sec_head(dept, '', dept, len(sids))
                if dept in view['open']:
                    for sid in sids:
                        ch_row(sid)
            hq = [p for p in S.state.staff if not p['site']]
            sec_head('공단 본부', '', '공단 본부', len(hq))
            if '공단 본부' in view['open'] or any(not p.get('present', True) for p in hq):
                for p in hq:
                    st = person_state(p)[0]
                    row = ui.element('div').classes('s4-ch' + (' on' if view['pid'] == p['id'] else ''))
                    row.on('click', lambda e, i=p['id']: pick_person(i))
                    with row:
                        ui.element('span').classes('dt').style(f'--c:{STATE_STYLE[st][0]}')
                        ui.label(disp_name(p)).classes('nm')
                        if st == '부재':
                            ui.label(p.get('absence') or '부재').classes('tg')

    # ── 가운데: 선택 사업장 ──
    def call_row(inc, k, r, kind, nrole):
        p = S.staff_of(inc['site'], r)
        st, ts = S.call_status(inc, r)
        absent = S.is_absent(inc, r) and st == '미호출'
        limit = S.no_response_min(inc) * 60
        if st == '응답':
            text, t, c = f'{S.hm(ts)} 응답 · 출동 중', '#1F5F95', B['blue']
        elif st == '호출 중':
            text, t, c = f'응답 대기 · {mmss(limit - (S.now() - ts))} 남음', YEL, '#E9B200'
        elif st == '미응답':
            text, t, c = f'{mmss(S.now() - ts)} 미응답', '#C62828', C['alarm']
        elif absent:
            text, t, c = f'{S.absence(inc, r)} · 건너뜀', '#A85400', C['warn']
        else:
            text, t, c = '대기', '#4B5563', GRAY
        now_ = r == nrole and kind in ('차순위 호출', '호출 전')
        ring = C['alarm'] if kind == '차순위 호출' else B['blue']
        row = ui.element('div').classes('s4-call' + (' now' if now_ else '') + (' skip' if absent else '')) \
            .style(f'--c:{ring if now_ else c};--t:{t}')
        with row:
            ui.label(str(k + 1)).classes('no')
            ui.html(avatar_html(p) if p else '')
            with ui.element('div').style('min-width:0'):
                ui.label(f"{p['name'] if p else '-'}  {rname(r)}").classes('nm')
                ui.label(p['phone'] if p else '-').classes('rl')
            ui.label(text).classes('st')
            if now_:
                b = ui.element('div').classes('s4-btn').style(f'--c:{ring}')
                b.on('click', lambda e, rr=r: S.notify(inc['id'], rr))
                with b:
                    ui.label('호출')
            elif st in ('호출 중', '미응답'):
                b = ui.element('div').classes('s4-btn ghost').style(f"--c:{B['blue']}")
                b.on('click', lambda e, rr=r: S.respond_call(inc['id'], rr))
                with b:
                    ui.label('응답 확인')
            else:
                ui.label('')

    def no_one(inc):
        with ui.element('div').classes('s4-none'):
            ui.icon('report')
            ui.label('호출 가능한 현장 인력 없음 → 소관 팀장·재난안전상황실 보고')
            ui.space()
            if S.call_status(inc, '팀장')[0] == '미호출':
                b = ui.element('div').classes('s4-btn').style(f"--c:{C['alarm']}")
                b.on('click', lambda e: (S.notify(inc['id'], '팀장'), S.notify(inc['id'], '재난안전상황실')))
                with b:
                    ui.label('보고')
            else:
                ui.label(f"{S.hm(S.call_status(inc, '팀장')[1])} 보고함").style('font-size:20px')

    def member_row(p):
        st, desc, _ = person_state(p)
        away = st == '부재'
        alt = substitute(p) if away else None
        row = ui.element('div').classes('s4-mem' + (' on' if view['pid'] == p['id'] else ''))
        row.on('click', lambda e, i=p['id']: pick_person(i))
        with row:
            ui.html(avatar_html(p))
            with ui.element('div').style('min-width:0'):
                ui.label(p['name']).classes('nm')
                ui.label(rname(p['role'])).classes('rl')
            with ui.element('div').style('text-align:right'):
                ui.html(pill_html(st, p.get('absence') if away else None))
                if alt:
                    ui.label(f"대신: {rname(alt['role'])} {alt['name']}").classes('ds alt')
                elif desc and not away:
                    ui.label(desc).classes('ds')
            ui.label(p['phone']).classes('ph')

    def week_table(ppl):
        td, start = today_idx(), week_start()
        ui.html('<div class="s4-wlegend">' + ''.join(
            f'<span><i style="background:{DAY_STYLE[k][0]}"></i>{k}</span>'
            for k in ['근무', '휴무', '연차', '교육', '출장', '병가']) + '</div>')
        with ui.element('div').classes('s4-wk head'):
            ui.label('인력')
            for d in range(7):
                dt = start + timedelta(days=d)
                ui.html(f'<div class="day{" today" if d == td else ""}">{DAYS[d]}'
                        f'<small>{dt.month}.{dt.day}{" 오늘" if d == td else ""}</small></div>')
        for p in ppl:
            row = ui.element('div').classes('s4-wk').style('cursor:pointer')
            row.on('click', lambda e, i=p['id']: pick_person(i))
            with row:
                ui.html(f'<div class="who">{p["name"]}<small>{rname(p["role"])}</small></div>')
                week = p.get('week') or ['근무'] * 7
                for d in range(7):
                    ui.html(day_html(week[d], d == td))

    def set_tab(t):
        view['tab'] = t
        refs['main'].refresh()

    def pick_inc(iid):
        view['inc'] = iid
        refs['main'].refresh()

    def build_main():
        sid = cur_site()
        site = S.state.sites[sid]
        incs = by_urgency(S.open_incidents(sid))
        ids = [i['id'] for i in incs]
        inc = S.get_incident(view['inc']) if view['inc'] in ids else (incs[0] if incs else None)
        ppl = site_people(sid)
        with ui.element('div').classes('s4-mh'):
            ui.label(f"# {site['name']}").classes('nm')
            ui.label(f"{site['dept']} · {site['gu']}").classes('sub')
            for i in incs:
                c = S.GRADE_COLOR[i['grade']]
                chip = ui.element('div').classes('s4-ic' + (' on' if inc and i['id'] == inc['id'] else '')) \
                    .style(f"--c:{c};--t:{KEY_TEXT.get(i['grade'], T['text'])}")
                chip.on('click', lambda e, x=i['id']: pick_inc(x))
                with chip:
                    ui.label(f"{short_tag(i)} · {i['grade']} · {S.ago(i['start'])}")
        with ui.element('div').classes('s4-tabs'):
            for t in TABS:
                tab = ui.element('div').classes('on' if view['tab'] == t else '')
                tab.on('click', lambda e, x=t: set_tab(x))
                with tab:
                    ui.label(t)
        with ui.element('div').classes('s4-mbody'):
            if view['tab'] == TABS[1]:
                week_table(ppl)
                return
            if inc:
                kind, nrole, _ = next_action(inc)
                with ui.element('div').classes('s4-st'):
                    ui.icon('directions_run')
                    ui.label('호출 순서')
                    how = '자동 차순위 호출' if S.is_high(inc) else '관제사가 차순위 호출'
                    ui.label(f"{inc['type']} · {inc['loc']} · {S.no_response_min(inc)}분 미응답 시 {how}").classes('r')
                with ui.element('div').style('display:flex;flex-direction:column;gap:10px'):
                    for k, r in enumerate(S.order_of(inc)):
                        call_row(inc, k, r, kind, nrole)
                    if kind in NO_ONE:
                        no_one(inc)
                logs = [l for l in inc['log'] if not l['text'].startswith(LOG_SKIP)][-8:]
                with ui.element('div').classes('s4-st'):
                    ui.icon('history')
                    ui.label('처리 경과')
                    ui.label('최근 8건 · 전체는 화면1 상황일지').classes('r')
                with ui.element('div').classes('s4-log'):
                    for l in reversed(logs):
                        with ui.element('div').classes('s4-lg' + (' memo' if l['kind'] == 'memo' else '')):
                            ui.label(S.hm(l['ts'])).classes('t')
                            ui.label(l['text']).classes('x')
            else:
                with ui.element('div').classes('s4-calm'):
                    ui.icon('check_circle')
                    ui.label('처리 중인 상황 없음')
            n_on = sum(1 for p in ppl if p.get('present', True))
            with ui.element('div').classes('s4-st'):
                ui.icon('groups')
                ui.label(f'사업장 인력 {len(ppl)}명')
                ui.label(f'오늘 근무 {n_on}명 · 누르면 오른쪽에 상세').classes('r')
            with ui.element('div'):
                for p in ppl:
                    member_row(p)

    # ── 오른쪽: 인력 프로필 ──
    def order_lines(p):
        role = p['role']
        if role == '팀장':
            return [('모든 상황', '내부 보고 · 재난안전상황실과 동시')]
        if not p['site']:
            return [('모든 상황', '내부 보고 · 동시')] if role == '재난안전상황실' else \
                   [('재난 등급 · 붕괴·지진·테러 등', '중대 상황 보고')]
        out = [(' · '.join(keys) + ' 상황', f'{order.index(role) + 1}순위')
               for keys, order in config.FIELD_ORDER if role in order]
        if role in config.FIELD_ORDER_DEFAULT:
            out.append(('그 외 상황', f'{config.FIELD_ORDER_DEFAULT.index(role) + 1}순위'))
        return out or [('-', '호출 순서에 없음')]

    def close_prof():
        view['pid'] = None
        refs['prof'].refresh()
        refs['main'].refresh()

    def build_prof():
        pid = view['pid']
        if pid is None:
            with ui.element('div').classes('s4-empty'):
                ui.icon('person_search')
                ui.html('가운데 인력 목록이나<br>왼쪽 공단 본부를 누르면<br>상세 정보가 표시됩니다')
            return
        p = S.state.staff[pid]
        st, desc, _ = person_state(p)
        site = S.state.sites[p['site']] if p['site'] else None
        recs = call_records(p)
        td = today_idx()
        with ui.element('div').classes('s4-ph'):
            ui.html(avatar_html(p, 'lg'))
            with ui.element('div').style('flex:1;min-width:0'):
                ui.label(disp_name(p)).classes('nm')
                ui.label(f"{rname(p['role'])} · " + (site['name'] if site else f"공단 본부 · {p['name']}")).classes('rl')
                ui.label(p['phone']).classes('tel')
            ui.button(icon='close', on_click=close_prof).props('flat round').style(f"color:{T['muted']}")
        with ui.element('div').classes('s4-pbody'):
            with ui.element('div'):
                ui.html(f'<div>{pill_html(st, (p.get("absence") or st) if st == "부재" else None)}'
                        f'<span style="font-size:20px;color:#4B5563;margin-left:12px">{desc}</span></div>')
            with ui.element('div').style('display:flex;flex-direction:column;gap:12px'):
                ui.label('오늘 근무 상태 변경').classes('s4-st')
                with ui.element('div').classes('s4-opts'):
                    on = p.get('present', True)
                    o = ui.label('근무 중').classes('s4-opt' + (' on' if on else '')).style(f"--c:{C['ok']}")
                    o.on('click', lambda e: S.set_presence(pid, True))
                    for r in config.ABSENCE_REASONS:
                        o = ui.label(r).classes('s4-opt' + (' on' if not on and p.get('absence') == r else '')) \
                            .style(f"--c:{C['warn']}")
                        o.on('click', lambda e, rr=r: S.set_presence(pid, False, rr))
                alt = substitute(p) if not p.get('present', True) else None
                if alt:
                    ui.label(f"호출 순서에서 건너뛰고 {rname(alt['role'])} {alt['name']}에게 먼저 연락합니다").classes('s4-note')
            if p.get('week'):
                with ui.element('div').style('display:flex;flex-direction:column;gap:12px'):
                    ui.label('이번 주 근무표').classes('s4-st')
                    with ui.element('div').classes('s4-week'):
                        for d in range(7):
                            with ui.element('div'):
                                ui.label(DAYS[d] + (' · 오늘' if d == td else ''))
                                ui.html(day_html(p['week'][d], d == td))
            with ui.element('div').style('display:flex;flex-direction:column;gap:10px'):
                ui.label('호출 순서').classes('s4-st')
                for cond, rank in order_lines(p):
                    ui.html(f'<div class="s4-kv"><span>{cond}</span><b>{rank}</b></div>')
            with ui.element('div').style('display:flex;flex-direction:column;gap:6px'):
                ui.label(f'오늘 호출·보고 {len(recs)}건').classes('s4-st')
                if not recs:
                    ui.label('기록 없음').style('font-size:20px;color:#4B5563')
                for i, n in recs[:10]:
                    ok = bool(n.get('resp'))
                    row = ui.element('div').classes('s4-rec')
                    row.on('click', lambda e, x=i['id']: S.select_incident(x))
                    with row:
                        ui.label(f"{S.hm(n['ts'])} {'자동 알람' if n.get('auto') else '호출'}").classes('t')
                        ui.label(f"{S.state.sites[i['site']]['name']} {short_tag(i)}"
                                 + (f" · {S.hm(n['resp'])} 응답" if ok else ''))

    def on_key(e):
        if e.key.name == 'Escape' and e.action.keydown and view['pid'] is not None:
            close_prof()

    def set_q(v):
        view['q'] = v or ''
        refs['side'].refresh()

    # ── 화면 배치 ──
    with screen_root():
        with header('대응인력 현황', left=lambda: live(build_counts, every=3)):
            live(build_modes, every=30)
            clock()
        with ui.element('div').classes('sg-body'):
            with ui.element('div').classes('s4-app'):
                with ui.element('div').classes('s4-col s4-nav'):
                    with ui.input(placeholder='사업장 · 이름 검색').props('outlined clearable hide-bottom-space') as qi:
                        with qi.add_slot('prepend'):
                            ui.icon('search')
                    qi.on_value_change(lambda e: set_q(e.value))
                    refs['side'] = live(build_side, every=15)
                with ui.element('div').classes('s4-col sg-panel s4-main'):
                    refs['main'] = live(build_main, every=3)
                with ui.element('div').classes('s4-col sg-panel s4-prof'):
                    refs['prof'] = live(build_prof, every=10)

    ui.timer(1, sync)
    ui.keyboard(on_key=on_key)