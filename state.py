"""
서버 공유 상태 + 상태 변경 함수.
- 모든 화면은 이 상태를 읽기만 한다.
- 상태 변경은 반드시 아래 함수로만 한다.
- 변경할 때마다 touch()로 version을 올린다. 화면은 version이 바뀌면 다시 그린다.
"""
import asyncio
import datetime as dt
import random
import time
import uuid

import config
import loader


def now():
    """현재 시각. 나중에 가상 시계(배속 재생)로 바꿀 때 이 함수만 수정한다."""
    return time.time()


class State:
    def __init__(self):
        self.version = 0
        self.sites = {}
        self.incidents = []
        self.staff = []
        self.selected_site = None
        self.selected_incident = None
        self.yesterday = {}
        self.operator = None         # 로그인한 관제사 이름
        self.login_at = None         # 근무 시작(로그인) 시각
        self.history = []            # 전일 종결 상황 (종결 기록 창에서만 표시)
        self.types = {}              # 엑셀 상황유형 {유형명: {category, grade, loc, desc}}
        self.checklists = {}         # 엑셀 체크리스트 {유형명: [{order, kind, text, basis}]}
        self.today_rows = []         # 엑셀 금일 상황
        self.yesterday_rows = []     # 엑셀 전일 기록
        self.site_events = []        # 엑셀 사업장 상태
        self.absences = []           # 엑셀 인력 부재
        self.facilities = {}         # 사업장별 중요설비 {사업장ID: [{names, focus, note}]}
        self.shift_override = None   # 근무 형태 수동 전환 (None = 시각 기준 자동)
        self.broadcasts = []         # 전체 전파 메시지 [{ts, text, by}]
        self._seq = 0


state = State()
SERVER_SESSION = uuid.uuid4().hex   # 서버를 켤 때마다 새로 생성 → 재시작하면 이전 로그인은 무효


def touch():
    state.version += 1

# ── 근무 형태 · 호출 순서 · 대응 인력 (화면1·4) ──
CALL_PRIORITY = ['미응답', '호출 중', '출동 중', '부재', '대기']   # 화면4 정렬·집계 순서


def shift_at(ts):
    """해당 시각의 근무 모드: 주간 / 야간·공휴일"""
    t = time.localtime(ts)
    day = t.tm_wday < 5 and config.DAY_HOURS[0] <= t.tm_hour < config.DAY_HOURS[1]
    return '주간' if day else '야간·공휴일'


def shift():
    """현재 모드 (수동 전환 값이 있으면 그 값)"""
    return state.shift_override or shift_at(now())


def set_shift(mode=None):
    """근무 형태 수동 전환 (None = 자동)"""
    state.shift_override = mode
    touch()


def field_order(type_, site_id=None):
    """상황 유형별 현장 대응 인력 호출 순서. 사업장에 없는 역할(예: 안전요원)은 제외"""
    order = next((o for keys, o in config.FIELD_ORDER if any(k in type_ for k in keys)),
                 config.FIELD_ORDER_DEFAULT)
    if site_id:
        order = [r for r in order if staff_of(site_id, r)] or config.FIELD_ORDER_DEFAULT
    return list(order)

def escalation(inc=None):
    """현장 호출 순서. 상황이 있으면 유형별, 없으면 기본 순서"""
    if inc is None:
        return list(config.FIELD_ORDER_DEFAULT)
    return field_order(inc['type'], inc['site'])


def _field_called(inc):
    """현장 대응 인력 호출을 한 번이라도 했는지"""
    return any(n['target'] in config.ESCALATION for n in inc['notices'])


def order_of(inc):
    """상황별 현장 호출 순서. 첫 호출 시점에 고정"""
    if _field_called(inc) and inc.get('order'):
        return inc['order']
    return escalation(inc)



def first_available(inc):
    """호출 순서에서 부재가 아닌 첫 인력 역할"""
    return next((r for r in order_of(inc) if not is_absent(inc, r)), None)


def staff_of(site_id, role):
    return next((p for p in state.staff if p['site'] == site_id and p['role'] == role), None)


def set_presence(pid, present, reason=''):
    """화면4 근무·부재 입력. 오늘 근무표 칸도 함께 변경"""
    p = state.staff[pid]
    p['present'] = present
    p['absence'] = '' if present else (reason or '기타')
    if 'week' in p:
        p['week'][time.localtime(now()).tm_wday] = '근무' if present else p['absence']
    touch()

def person_status(site_id, role):
    """화면4 인력 상태 (상태, 시각, 상황). 해당 사업장 미조치 상황 중 등급이 높은 건 기준
    상태: 미응답 / 호출 중 / 출동 중(응답) / 부재 / 대기"""
    incs = sorted(open_incidents(site_id), key=lambda i: (GRADE_RANK[i['grade']], i['start']))
    for inc in incs:
        st, ts = call_status(inc, role)
        if st != '미호출':
            return ('출동 중' if st == '응답' else st), ts, inc
    p = staff_of(site_id, role)
    if p and not p.get('present', True):
        return '부재', None, None
    return '대기', None, None


def site_call_status(site_id):
    """사업장 대표 상태 = 인력 상태 중 가장 시급한 것"""
    sts = [person_status(site_id, r)[0] for r in config.ESCALATION]
    return min(sts, key=CALL_PRIORITY.index)


def _auto_call(inc):
    """재난·긴급 접수와 동시에 첫 순위(부재자 제외) 단말 자동 알람. 시각 = 접수 시각"""
    target = first_available(inc)
    if not target:
        return
    ts = inc['start']
    inc['order'] = escalation(inc)               # 자동 알람 시 호출 순서 고정
    inc['notices'].append({'target': target, 'ts': ts, 'resp': None, 'auto': True})
    _log(inc, f'자동 알람 · {target} 단말', ts=ts)
    for p in _staff(inc, target):
        p['status'], p['ts'] = '통보', ts
    _auto_check(inc, target, ts=ts) or _auto_check(inc, '현장 담당자', ts=ts)
    if inc['stage'] == config.STAGES[0]:
        inc['stage'] = config.STAGES[1]
        _log(inc, f'처리 단계 → {inc["stage"]}', ts=ts)

# ── 엑셀 불러오기 ──
def load_scenario():
    data = loader.load()
    state.types, state.checklists = data['types'], data['checklists']
    state.today_rows, state.yesterday_rows = data['today'], data['yesterday']
    state.site_events, state.absences = data['site_events'], data['absences']
    n_check = sum(len(v) for v in state.checklists.values())
    print(f'[엑셀] 상황유형 {len(state.types)}개 · 체크리스트 {n_check}항목 · 금일 상황 {len(state.today_rows)}행 · '
          f'전일 기록 {len(state.yesterday_rows)}건 · 사업장 상태 {len(state.site_events)}건 · 인력 부재 {len(state.absences)}건')
    for w in data['warnings']:
        print('[엑셀 확인]', w)

    fac = loader.load_facilities()
    state.facilities = fac['facilities']
    n_equip = sum(len(f['names']) for v in state.facilities.values() for f in v)
    print(f'[설비] 사업장 {len(state.facilities)}곳 · 중요설비 {n_equip}개')
    for w in fac['warnings']:
        print('[설비 확인]', w)


# ── 조회 ──
GRADE_RANK = {g['name']: i for i, g in enumerate(config.GRADES)}
GRADE_COLOR = {g['name']: g['color'] for g in config.GRADES}
STAGE_INDEX = {s: i for i, s in enumerate(config.STAGES)}


def is_open(inc):
    """미조치: 조치 완료 전 단계"""
    return STAGE_INDEX[inc['stage']] < STAGE_INDEX[config.ACTION_DONE_STAGE]


def needs_report(inc):
    """보고 미작성: 조치 완료 후 보고 전"""
    return inc['stage'] == config.ACTION_DONE_STAGE


def is_closed(inc):
    return inc['stage'] == config.DONE_STAGE


def is_high(inc):
    return inc['grade'] in config.AUTO_SELECT_GRADES


def card_of(inc):
    """화면1 카드 분류. 종결 건은 None"""
    if needs_report(inc):
        return '보고 미작성'
    if not is_open(inc):
        return None
    if is_high(inc):
        return '긴급 이상 미조치'
    return '미조치'


def open_incidents(site_id=None):
    return [i for i in state.incidents
            if is_open(i) and (site_id is None or i['site'] == site_id)]


def sorted_incidents():
    """미조치 → 보고 미작성 → 종결 순. 각 묶음 안에서 등급순 → 경과 시간 긴 순"""
    def group(i):
        return 0 if is_open(i) else 1 if needs_report(i) else 2
    return sorted(state.incidents, key=lambda i: (group(i), GRADE_RANK[i['grade']], i['start']))


def report_overdue(s):
    """미연계 사업장 정기 보고 지연 여부"""
    return not s['linked'] and now() - s['last_report'] >= config.REPORT_DELAY_HOURS * 3600


def site_status(site_id):
    """사업장 상태: 확인 불가 / 미조치 / 확인 필요 / 이상 / 정상
    확인 불가 = AI·경보 연계 사업장 연결 끊김 (시스템 장애)
    확인 필요 = 미연계 사업장 정기 보고 지연 (관제사가 전화 등으로 확인)"""
    s = state.sites[site_id]
    if s['linked'] and not s['connected']:
        return '확인 불가'
    if open_incidents(site_id):
        return '미조치'
    if report_overdue(s):
        return '확인 필요'
    if any(v != '정상' for v in s['equip'].values()) or s['aux'] or s['report'] != '정상':
        return '이상'
    return '정상'


def unknown_reason(site_id):
    s = state.sites[site_id]
    if s['linked'] and not s['connected']:
        return '시스템 연결 끊김'
    if report_overdue(s):
        return f"보고 지연 · {ago(s['last_report'])} 전 보고"
    return ''


STATUS_COLOR = {'미조치': config.COLORS['alarm'], '이상': config.COLORS['warn'],
                '확인 필요': config.COLORS['pending'], '확인 불가': config.COLORS['unknown'],
                '정상': config.COLORS['ok']}


def summary():
    total = len(state.incidents)
    opened = len(open_incidents())
    rate = round((total - opened) / total * 100) if total else 0
    return {'today': total, 'open': opened, 'rate': rate}


def get_incident(iid):
    """금일 상황 + 전일 기록에서 찾기"""
    return next((i for i in state.incidents + state.history if i['id'] == iid), None)

# ── 화면1 운영 지표 (상황일지 시각으로 계산) ──
def first_call_ts(inc):
    """첫 현장 호출·외부 신고 시각 (없으면 None)"""
    ts = [n['ts'] for n in inc['notices'] if n['target'] in config.ESCALATION or n['target'] in EXTERNAL]
    return min(ts) if ts else None


def stage_times(inc):
    """처리 단계 진입 시각 {단계: 시각} — 상황일지 '처리 단계 → X' 기록 기준"""
    out = {config.STAGES[0]: inc['start']}
    for l in inc['log']:
        if l['text'].startswith('처리 단계 → '):
            out.setdefault(l['text'].split('→ ', 1)[1], l['ts'])
    if inc.get('closed'):
        out.setdefault(config.DONE_STAGE, inc['closed'])
    return out


def ops_metrics():
    """초동 시간 · 조치 시간 · 단계별 건수·머문 시간 · 미응답 호출 · 유형별 접수 · 다발 사업장"""
    incs = state.incidents

    def avg_min(xs):
        return sum(xs) / len(xs) / 60 if xs else None

    first = [first_call_ts(i) - i['start'] for i in incs if first_call_ts(i)]
    act = [stage_times(i)[config.ACTION_DONE_STAGE] - i['start']
           for i in incs if config.ACTION_DONE_STAGE in stage_times(i)]
    dwell = {s: [] for s in config.STAGES[:-1]}
    for i in incs:
        st = stage_times(i)
        seq = [s for s in config.STAGES if s in st]
        for a, b in zip(seq, seq[1:]):
            if a in dwell:
                dwell[a].append(st[b] - st[a])
        if not is_closed(i) and i['stage'] in st and i['stage'] in dwell:
            dwell[i['stage']].append(now() - st[i['stage']])        # 지금 머무는 시간 포함
    no_resp = [(i, r, call_status(i, r)[1]) for i in incs if not is_closed(i)
               for r in order_of(i) if call_status(i, r)[0] == '미응답']
    per_site = {}
    for i in incs:
        per_site[i['site']] = per_site.get(i['site'], 0) + i['repeat']
    top = sorted(per_site.items(), key=lambda x: -x[1])[:3]
    return {'first_avg': avg_min(first), 'first_n': len(first),
            'act_avg': avg_min(act), 'act_n': len(act),
            'stage_count': {s: sum(1 for i in incs if i['stage'] == s) for s in config.STAGES},
            'dwell_avg': {s: avg_min(v) for s, v in dwell.items()},
            'no_resp': no_resp,
            'by_cat': {c: sum(1 for i in incs if i['category'] == c) for c in config.CATEGORIES},
            'top_sites': [(sid, state.sites[sid]['name'], n) for sid, n in top]}


def broadcast(text, by=None, to='전체'):
    """전파 메시지 기록. to: 받는 사람 표시 (전체 / 공단 상급 보고 / 사업장). 빈 내용이면 False"""
    text = (text or '').strip()
    if not text:
        return False
    state.broadcasts.append({'ts': now(), 'text': text, 'by': by or '관제사', 'to': to or '전체'})
    touch()
    return True

# ── 상황 변경 ──
def _log(inc, text, kind='auto', author=None, ts=None):
    """상황일지 기록. kind: auto(자동 기록) / memo(조치 메모)"""
    inc['log'].append({'ts': ts or now(), 'kind': kind, 'text': text, 'author': author})


def _new_incident(iid, site, loc, type_, grade, entry, desc, start, equip=None, category=None, video=''):
    """상황 기록 1건 생성 (목록에는 넣지 않음)"""
    info = state.types.get(type_, {})
    inc = {'id': iid, 'site': site, 'loc': loc, 'type': type_,
           'category': category or info.get('category') or config.CATEGORIES[0],
           'grade': grade, 'entry': entry, 'desc': desc,
           'start': start, 'stage': config.STAGES[0], 'repeat': 1, 'log': [],
           'checks': {},          # {체크리스트 번호: 체크 시각}
           'notices': [],         # [{target, ts, resp}] 호출·신고·보고 기록
           'order': field_order(type_, site),   # 현장 호출 순서 (유형별)
           'handler': '',         # 담당자 이름 (종결 필수)
           'equip': equip,        # 연결 설비 (설비 경보 해제용)
           'video': video or '',  # 화면5 영상 파일 (엑셀 지정)
           'report': {'loc_detail': '', 'damage': '', 'result': '', 'cause': ''}}
    _log(inc, f'접수 · {entry} · 등급 {grade} · {shift_at(start)}', ts=start)
    return inc


def create_incident(site, loc, type_, grade=None, entry='신고', desc='',
                    equip=None, minutes_ago=0, category=None, video='', auto=True):
    """상황 접수. 같은 사업장·같은 유형이 미조치 중이면 1건으로 묶고 반복 횟수(총 발생 횟수) 증가
    재난·긴급은 접수와 동시에 현장 호출 첫 순위(부재자 제외)에게 자동 알람 (auto=False면 생략)"""
    info = state.types.get(type_, {})
    grade = grade or info.get('grade') or config.GRADES[-1]['name']
    if equip is None and entry == '센서·경보':
        equip = equip_of(type_)
    start = now() - minutes_ago * 60
    same = [i for i in state.incidents if i['site'] == site and i['type'] == type_]
    count = max((i['repeat'] for i in same), default=0) + 1

    for inc in same:
        if is_open(inc):
            inc['repeat'] = count
            _log(inc, f'동일 상황 재접수 · 총 {count}회 발생', ts=start)
            if GRADE_RANK[grade] < GRADE_RANK[inc['grade']]:
                _log(inc, f'등급 상향 · {inc["grade"]} → {grade}', ts=start)
                inc['grade'] = grade
            if is_high(inc):
                state.selected_incident, state.selected_site = inc['id'], site
            touch()
            return inc

    state._seq += 1
    inc = _new_incident(state._seq, site, loc, type_, grade, entry, desc, start, equip, category, video)
    inc['repeat'] = count
    state.incidents.append(inc)
    if equip and state.sites[site]['linked']:
        state.sites[site]['equip'][equip] = '경보'
    if auto and grade in config.AUTO_CALL_GRADES:
        _auto_call(inc)
    if grade in config.AUTO_SELECT_GRADES:
        state.selected_incident = inc['id']
        state.selected_site = site
    touch()
    return inc


def advance(iid):
    """다음 처리 단계로. 조치 완료까지만 (보고 완료는 close_incident로)"""
    inc = get_incident(iid)
    if not inc or not is_open(inc):
        return
    inc['stage'] = config.STAGES[STAGE_INDEX[inc['stage']] + 1]
    _log(inc, f'처리 단계 → {inc["stage"]}')
    if inc['stage'] == config.ACTION_DONE_STAGE:
        _clear_equip(inc)
    touch()


def _staff(inc, role):
    """상황 사업장의 해당 역할 인력 (공단 본부 인력은 사업장 구분 없음)"""
    return [p for p in state.staff if p['role'] == role and p['site'] in (inc['site'], None)]

def equip_of(type_):
    """상황유형 → 연결된 설비명 (없으면 None)"""
    return next((e for e, ts in config.EQUIPMENT_TYPES.items() if type_ in ts), None)


def _clear_equip(inc):
    """설비 경보 해제: 같은 사업장·같은 설비의 다른 미조치 건이 없으면 '정상'으로"""
    e, s = inc.get('equip'), state.sites.get(inc['site'])
    if not e or not s or e not in s['equip']:
        return
    if not any(i is not inc and i['site'] == inc['site'] and i.get('equip') == e and is_open(i)
               for i in state.incidents):
        s['equip'][e] = '정상'

def checklist_for(inc):
    """상황 유형의 체크리스트. 엑셀에 없으면 공통 체크리스트"""
    return state.checklists.get(inc['type']) or config.DEFAULT_CHECKLIST

def _auto_check(inc, keyword, ts=None):
    """조치 내용에 keyword가 들어간 첫 미체크 '전파'·'지시' 항목을 자동 체크. 체크했으면 True"""
    for idx, it in enumerate(checklist_for(inc)):
        if it['kind'] in ('전파', '지시') and keyword in it['text'] and idx not in inc['checks']:
            inc['checks'][idx] = ts or now()
            _log(inc, f"체크 · {it['text']} (자동)", ts=ts)
            return True
    return False

EXTERNAL = ('119', '112')


def notify(iid, target):
    """호출·신고·보고 기록. 화면1·4 호출 상태와 연동
    - 119·112: 외부 신고 / 현장 대응 인력: 현장 호출 / 재난안전상황실·팀장·경영진: 내부 보고 / 그 외: 기관·업체 연락"""
    inc = get_incident(iid)
    if not inc:
        return
    if target in config.ESCALATION and not _field_called(inc):
        inc['order'] = escalation(inc)           # 첫 현장 호출 시 호출 순서 고정
    inc['notices'].append({'target': target, 'ts': now(), 'resp': None})
    if target in EXTERNAL:
        text = f'{target} 신고 (자동 신고 연동)'
    elif target in config.REPORT_LINE:
        text = f'{target} 보고'
    elif target in config.ESCALATION:
        text = f'호출 · {target}'
    else:
        text = f'연락 · {target}'
    _log(inc, text)
    for p in _staff(inc, target):
        p['status'], p['ts'] = '통보', now()
    if target in EXTERNAL:
        _auto_check(inc, f'{target} 신고')
    elif target in config.ESCALATION:
        _auto_check(inc, target) or _auto_check(inc, '현장 담당자')
    elif target in config.REPORT_NOW:
        _auto_check(inc, '재난안전상황실') or _auto_check(inc, '팀장')
    else:
        _auto_check(inc, target)
    if target in config.ESCALATION and inc['stage'] == config.STAGES[0]:
        inc['stage'] = config.STAGES[1]
        _log(inc, f'처리 단계 → {inc["stage"]}')
    touch()


def respond_call(iid, target):
    """호출 응답 기록. 관제사가 전화 등으로 응답을 받은 뒤 '응답 확인'을 누름
    응답하면 '사업장 통보' → '현장 확인' 자동 전환"""
    inc = get_incident(iid)
    sent = [n for n in inc['notices'] if n['target'] == target] if inc else []
    if not sent or sent[-1].get('resp'):
        return
    sent[-1]['resp'] = now()
    _log(inc, f'응답 · {target}')
    for p in _staff(inc, target):
        p['status'], p['ts'] = '응답', now()
    if target in config.ESCALATION and inc['stage'] == '사업장 통보':
        inc['stage'] = '현장 확인'
        _log(inc, '처리 단계 → 현장 확인')
    touch()


def no_response_min(inc):
    """등급별 미응답 판정 시간(분)"""
    return config.NO_RESPONSE_MIN.get(inc['grade'], 3)


def is_absent(inc, role):
    """해당 역할 인력이 모두 부재면 True (화면4 재실 여부)"""
    ppl = _staff(inc, role)
    return bool(ppl) and all(not p.get('present', True) for p in ppl)


def absence(inc, role):
    """부재 사유 (예: 연차)"""
    return next((p.get('absence') or '부재' for p in _staff(inc, role) if not p.get('present', True)), '')


def needs_external(inc, target):
    """체크리스트에 '119 신고'·'112 신고'가 있는 유형이면 True (버튼 강조용)"""
    return any(f'{target} 신고' in it['text'] for it in checklist_for(inc))


def call_status(inc, target):
    """(상태, 시각). 미호출 / 호출 중 / 응답 / 미응답 / 신고 완료(119·112) / 통보 완료(내부 보고)"""
    sent = [n for n in inc['notices'] if n['target'] == target]
    if not sent:
        return '미호출', None
    last = sent[-1]
    if target in EXTERNAL:
        return '신고 완료', last['ts']
    if target in config.REPORT_LINE:
        return '통보 완료', last['ts']
    if target not in config.ESCALATION:
        return '연락 완료', last['ts']          # 구청·설비·업체: 응답 대기 없음
    if last.get('resp'):
        return '응답', last['resp']
    if now() - last['ts'] >= no_response_min(inc) * 60:
        return '미응답', last['ts']
    return '호출 중', last['ts']


def can_call(inc, target):
    """현장 호출: 앞 순위가 미응답이거나 부재면 가능 / 내부 보고·기관·신고: 바로 가능"""
    if call_status(inc, target)[0] != '미호출':
        return False
    order = order_of(inc)
    if target in order:
        idx = order.index(target)
        if idx == 0:
            return True
        prev = order[idx - 1]
        st = call_status(inc, prev)[0]
        return st == '미응답' or (is_absent(inc, prev) and (st != '미호출' or can_call(inc, prev)))
    return True


def needs_senior(inc):
    """경영진·재난안전실장 보고 대상: 재난 등급 또는 중대 유형 (매뉴얼: 붕괴·테러·지진 등)"""
    return inc['grade'] == '재난' or any(k in inc['type'] for k in config.SENIOR_KEYWORDS)


def report_targets(inc):
    """이 상황의 내부 보고 대상: 재난안전상황실·팀장 (+ 중대 상황이면 경영진)"""
    return list(config.REPORT_NOW) + (['경영진'] if needs_senior(inc) else [])


def report_timing(inc):
    """내부 보고 시점 안내"""
    if is_high(inc) or inc['category'] == '안전사고':
        t = '즉시'
    elif inc['grade'] == '주의':
        t = '현장 확인 후'
    else:
        t = '피해 발생 시'
    return {'재난안전상황실': t, '팀장': t, '경영진': '즉시' if needs_senior(inc) else '필요 시'}

def add_memo(iid, text, author=None):
    """조치 메모. 빈 내용이면 False"""
    inc = get_incident(iid)
    text = (text or '').strip()
    if not inc or not text:
        return False
    _log(inc, text, kind='memo', author=author)
    touch()
    return True


def toggle_check(iid, idx, text):
    """체크리스트 항목 체크/해제. 체크 시각을 상황일지에 기록"""
    inc = get_incident(iid)
    if not inc:
        return
    if idx in inc['checks']:
        del inc['checks'][idx]
        _log(inc, f'체크 해제 · {text}')
    else:
        inc['checks'][idx] = now()
        _log(inc, f'체크 · {text}')
    touch()


def set_handler(iid, name):
    """담당자 이름 입력 (입력 중 화면이 다시 그려지지 않도록 touch 안 함)"""
    inc = get_incident(iid)
    if inc:
        inc['handler'] = name or ''


def set_report(iid, field, value):
    """보고서 항목 입력 (입력 중 화면이 다시 그려지지 않도록 touch 안 함)"""
    inc = get_incident(iid)
    if inc and field in inc['report']:
        inc['report'][field] = value or ''


REPORT_REQUIRED = {'loc_detail': '세부 위치', 'damage': '피해 내용', 'result': '조치 결과'}


def close_missing(inc):
    """종결 전 누락 항목 목록. 빈 목록이면 종결 가능"""
    miss = []
    if not needs_report(inc):
        miss.append('조치 완료 단계')
    if not inc['handler'].strip():
        miss.append('담당자 이름')
    if not any(l['kind'] == 'memo' for l in inc['log']):
        miss.append('조치 메모 1건')
    miss += [label for key, label in REPORT_REQUIRED.items() if not inc['report'][key].strip()]
    return miss


def close_incident(iid):
    """보고 완료·종결. 누락 항목이 있으면 False"""
    inc = get_incident(iid)
    if not inc or close_missing(inc):
        return False
    inc['stage'] = config.DONE_STAGE
    inc['closed'] = now()
    _log(inc, f'보고 완료 · 종결 · 담당 {inc["handler"]}')
    if state.selected_incident == iid:
        state.selected_incident = None
    touch()
    return True

def video_confirm(iid, by=None):
    """화면5 [실제 상황]: 영상 확인 결과를 상황일지에 기록 (처리는 화면1에서 계속)"""
    inc = get_incident(iid)
    if not inc or is_closed(inc):
        return
    inc['video_check'] = ('실제 상황', now())
    _log(inc, '영상 확인 · 실제 상황 (화면5)', author=by)
    touch()


def close_false_alarm(iid, by=None):
    """화면5 [오경보]: 오경보로 바로 종결. 보고서 자동 작성, 선택 해제"""
    inc = get_incident(iid)
    if not inc or is_closed(inc):
        return
    inc['video_check'] = ('오경보', now())
    inc['false_alarm'] = True
    inc['handler'] = inc['handler'] or (by or '관제사')
    inc['report'].update(loc_detail=inc['loc'], damage='없음', result='영상 확인 결과 오경보, 종결', cause='오경보')
    _log(inc, '영상 확인 · 오경보 종결 (화면5)', author=by)
    inc['stage'] = config.DONE_STAGE
    inc['closed'] = now()
    _clear_equip(inc)
    if state.selected_incident == iid:
        state.selected_incident = state.selected_site = None
    touch()


_select_listeners = []          # 화면3·4가 등록: 화면1에서 상황을 누르면 바로 호출


def on_select(fn):
    _select_listeners.append(fn)


def off_select(fn):
    if fn in _select_listeners:
        _select_listeners.remove(fn)


def select_incident(iid):
    """화면1에서 상황 선택 → 화면3·4에 바로 알림"""
    inc = get_incident(iid)
    state.selected_incident = iid
    state.selected_site = inc['site'] if inc else None
    state.select_seq = getattr(state, 'select_seq', 0) + 1
    touch()
    for fn in list(_select_listeners):
        try:
            fn()
        except Exception as e:
            print('[연동 오류]', e)


def select_site(site_id):
    state.selected_site = site_id
    touch()


def login(name):
    state.operator = name.strip()
    state.login_at = now()
    touch()


def logout():
    state.operator = state.login_at = None
    touch()


# ── 사업장 변경 ──
def toggle_connection(site_id):
    s = state.sites[site_id]
    s['connected'] = not s['connected']
    touch()

def manual_report(site_id, status='정상', text='', by=None):
    """미연계 사업장 정기 보고 입력 (관제사가 전화 등으로 확인 후 입력)
    status: 정상 / 이상. 이상이면 text(이상 내용) 필수. 모든 보고는 report_log에 누적"""
    s = state.sites[site_id]
    s['last_report'], s['report'] = now(), status
    s['report_note'] = text if status != '정상' else ''
    s.setdefault('report_log', []).append(
        {'ts': now(), 'status': status, 'text': text or '정상 확인', 'by': by or '관제사'})
    touch()

# ── 미연계 사업장 정기 보고 자동 수신 ──
REPORT_EVERY_MIN = (30, 90)        # 자동 보고 간격(분) 범위


def auto_reports():
    """미연계 사업장마다 30~90분 간격으로 정기 보고 수신. 보고 지연(hold) 사업장은 제외"""
    t = now()
    changed = False
    for sid, s in state.sites.items():
        if s['linked'] or s.get('hold'):
            continue
        if 'next_report' not in s:
            s['next_report'] = s['last_report'] + random.randint(*REPORT_EVERY_MIN) * 60
        if t < s['next_report']:
            continue
        s['last_report'] = t
        text = '정상 보고' if s['report'] == '정상' else f"이상 지속 · {s.get('report_note') or '이상'}"
        s.setdefault('report_log', []).append({'ts': t, 'status': s['report'], 'text': text, 'by': '사업장 담당자'})
        s['next_report'] = t + random.randint(*REPORT_EVERY_MIN) * 60
        changed = True
    if changed:
        touch()

def auto_escalate():
    """재난·긴급: 앞 순위가 미응답이면 다음 순위(부재 제외)에게 자동 알람. 주의·알림은 관제사가 직접 호출"""
    t = now()
    changed = False
    for inc in state.incidents:
        if not is_open(inc) or not is_high(inc):
            continue
        order = order_of(inc)
        for idx, r in enumerate(order):
            if call_status(inc, r)[0] != '미응답':
                continue
            rest = order[idx + 1:]
            if any(call_status(inc, q)[0] != '미호출' for q in rest):
                continue                                   # 이미 다음 순위를 부름
            nxt = next((q for q in rest if not is_absent(inc, q)), None)
            if not nxt:
                break                                      # 전원 미응답 → 화면4에서 팀장·재난안전상황실 보고
            inc['notices'].append({'target': nxt, 'ts': t, 'resp': None, 'auto': True})
            _log(inc, f'자동 차순위 호출 · {nxt} 단말 ({r} 미응답)', ts=t)
            for p in _staff(inc, nxt):
                p['status'], p['ts'] = '통보', t
            _auto_check(inc, nxt, ts=t)
            changed = True
            break
    if changed:
        touch()

async def _report_loop():
    while True:
        auto_reports()
        auto_escalate()
        await asyncio.sleep(5)


def start_demo():
    """main.py에서 서버 시작 시 1번 호출"""
    asyncio.create_task(_report_loop())

# ── 대응 인력 변경 ──
def call_first(site_id):
    for p in state.staff:
        if p['site'] == site_id and p['role'] == config.ESCALATION[0]:
            p['status'], p['ts'] = '통보', now()


def respond(person_id, status):
    p = state.staff[person_id]
    p['status'], p['ts'] = status, now()
    touch()


def escalate(person_id):
    p = state.staff[person_id]
    idx = config.ESCALATION.index(p['role'])
    if idx + 1 < len(config.ESCALATION):
        nxt_role = config.ESCALATION[idx + 1]
        for q in state.staff:
            if q['role'] == nxt_role:
                q['status'], q['ts'] = '통보', now()
    touch()


# ── 엑셀 → 초기 상태 ──
DAYS = ['월', '화', '수', '목', '금', '토', '일']


def _progress(inc, step, call=None, resp=None, action=None, close=None, rep=None, people=True):
    """처리 단계까지 상황일지·호출·체크리스트 자동 작성. 시각은 절대 시각(초), 비우면 자동"""
    if step in (None, config.STAGES[0]):
        return
    s0 = inc['start']
    rep = rep or {}
    fa = step == '오경보 종결'
    level = 4 if fa else STAGE_INDEX[step]                   # 1 사업장 통보 · 2 현장 확인 · 3 조치 완료 · 4 보고 완료
    role = first_available(inc)
    inc['order'] = escalation(inc)
    call = call or (s0 if is_high(inc) else s0 + 60)
    if role:
        auto = is_high(inc)
        inc['notices'].append({'target': role, 'ts': call, 'resp': None, **({'auto': True} if auto else {})})
        _log(inc, f'자동 알람 · {role} 단말' if auto else f'호출 · {role}', ts=call)
    _log(inc, f'처리 단계 → {config.STAGES[1]}', ts=call)
    done = [call]
    if level >= 2:
        resp = resp or call + 120
        if role:
            inc['notices'][-1]['resp'] = resp
            _log(inc, f'응답 · {role}', ts=resp)
        _log(inc, f'처리 단계 → {config.STAGES[2]}', ts=resp)
        done.append(resp)
    if inc['entry'] == 'CCTV' and not fa:                       # CCTV 접수 건: 영상 확인 결과 기록
        inc['video_check'] = ('실제 상황', call)
        _log(inc, '영상 확인 · 실제 상황 (화면5)', ts=call)
    if fa:
        close = close or (resp or call) + 120
        inc.update(video_check=('오경보', close), false_alarm=True, handler=rep.get('handler') or '관제사',
                   stage=config.DONE_STAGE, closed=close)
        inc['report'].update(loc_detail=inc['loc'], damage='없음', result='영상 확인 결과 오경보, 종결', cause='오경보')
        if rep.get('memo'):
            _log(inc, rep['memo'], kind='memo', author=rep.get('handler') or '관제사', ts=close - 30)
        _log(inc, '영상 확인 · 오경보 종결 (화면5)', ts=close)
        items = checklist_for(inc)[:1]
        for idx, _ in enumerate(items):
            inc['checks'][idx] = call
        if people:
            _clear_equip(inc)
        return
    if level >= 3:
        action = action or done[-1] + 30 * 60
        memo = rep.get('memo') or rep.get('result')
        if memo:
            _log(inc, memo, kind='memo', author=rep.get('handler') or '관제사', ts=action - 60)
        _log(inc, f'처리 단계 → {config.ACTION_DONE_STAGE}', ts=action)
        done.append(action)
    items = checklist_for(inc)
    n = len(items) if level >= 3 else (len(items) + 1) // 2 if level == 2 else 1
    a, b = done[0], done[-1]
    for idx in range(min(n, len(items))):
        inc['checks'][idx] = a + (b - a) * idx / max(n - 1, 1)
    inc['stage'] = config.STAGES[min(level, 3)]
    if level >= 3 and people:
        _clear_equip(inc)
    if level == 4:
        close = close or action + 20 * 60
        inc['handler'] = rep.get('handler') or '관제사'
        inc['report'].update({k: rep.get(k, '') for k in ('loc_detail', 'damage', 'result', 'cause')})
        inc['stage'], inc['closed'] = config.DONE_STAGE, close
        _log(inc, f'보고 완료 · 종결 · 담당 {inc["handler"]}', ts=close)
    if people and role and not is_closed(inc):
        for p in _staff(inc, role):
            p['status'], p['ts'] = ('응답', resp) if level >= 2 else ('통보', call)


def _seed_today():
    """금일 상황 시트 → 처리 단계까지 반영된 상황 목록 (오래된 접수부터)"""
    t0 = now()
    ts = lambda m: None if m is None else t0 - m * 60
    for e in state.today_rows:
        merged = any(i['site'] == e['site'] and i['type'] == e['type'] and is_open(i) for i in state.incidents)
        step = None if merged else e['step']
        inc = create_incident(e['site'], e['loc'], e['type'], e['grade'], e['entry'], e['desc'],
                              minutes_ago=e['ago'], video=e['video'], auto=step in (None, config.STAGES[0]))
        if not merged:
            _progress(inc, step, ts(e['call']), ts(e['resp']), ts(e['action']), ts(e['close']), e['rep'])
    for inc in state.incidents:
        inc['log'].sort(key=lambda l: l['ts'])


def _seed_history():
    """전일 기록 시트 → 종결 상황 (금일 목록·지표와 분리)"""
    base = dt.datetime.combine(dt.date.fromtimestamp(now()) - dt.timedelta(days=1), dt.time()).timestamp()
    at = lambda m: None if m is None else base + m * 60
    state.history = []
    for k, e in enumerate(state.yesterday_rows, 1):
        inc = _new_incident(-k, e['site'], e['loc'], e['type'], e['grade'], e['entry'], e['desc'],
                            at(e['start_min']))
        _progress(inc, config.DONE_STAGE, at(e['call']), at(e['resp']), at(e['action']), at(e['close']),
                  e['rep'], people=False)
        inc['log'].sort(key=lambda l: l['ts'])
        state.history.append(inc)
    n = len(state.history)
    state.yesterday = {'today': n, 'open': 0, 'rate': 100 if n else 0}


def _apply_site_events():
    """사업장 상태 시트 → 보고 지연 · 이상 보고 · 정상 보고 · 보조설비 이상 · 연결 끊김/복구"""
    t0 = now()
    for e in state.site_events:
        s, ts, note = state.sites.get(e['site']), t0 - e['ago'] * 60, e['note']
        if not s:
            continue
        kind = e['kind']
        if kind == '보고 지연':
            mins = float(note) if note else config.REPORT_DELAY_HOURS * 60
            s['last_report'], s['hold'] = t0 - mins * 60, True
        elif kind in ('이상 보고', '정상 보고'):
            bad = kind == '이상 보고'
            s.update(report='이상' if bad else '정상', report_note=(note or '이상') if bad else '',
                     last_report=ts, hold=False)
            s.setdefault('report_log', []).append({'ts': ts, 'status': s['report'],
                                                   'text': (note or '이상') if bad else '정상 확인',
                                                   'by': '사업장 담당자'})
        elif kind == '보조설비 이상':
            s['aux'] = note or None
        elif kind in ('연결 끊김', '연결 복구'):
            s['connected'] = kind == '연결 복구'


def _apply_absences(today):
    """인력 부재 시트 → 근무표 칸 + 오늘 부재"""
    for a in state.absences:
        if a['site'] is None:                                   # 공단 본부: 직위로 찾음
            p = next((q for q in state.staff if q['site'] is None and q.get('title') == a['role']), None)
        else:
            p = staff_of(a['site'], a['role'])
        if not p:
            where = state.sites[a['site']]['name'] if a['site'] else '공단 본부'
            print(f"[엑셀 확인] 인력 부재: {where}에 {a['role']} 없음")
            continue
        d = today if a['day'] == '오늘' else DAYS.index(a['day'])
        p['week'][d] = a['reason']
        if d == today:
            p['present'], p['absence'] = False, a['reason']


def reset_sample():
    """서버 시작 시 초기 상태: 사업장·인력 기본값 + 엑셀(사업장 상태·인력 부재·금일 상황·전일 기록)"""
    state.sites = {
        s['id']: {**s, 'connected': True,
                  'equip': {e: '정상' for e in config.EQUIPMENT} if s['linked'] else {},
                  'aux': None, 'report': '정상', 'last_report': now() - 3600}
        for s in config.SITES
    }
    for i, sid in enumerate(sorted(state.sites)):               # 정기 보고 시각 분산
        if not state.sites[sid]['linked']:
            state.sites[sid]['last_report'] = now() - (12 + i * 3) * 60
    _apply_site_events()

    # 대응 인력 (이름·번호는 가상): 사업장마다 현장 인력(유형별) + 소관 팀장 / 공단 본부
    sur = '김이박최정강조윤장임한오서신권황안송류홍'
    state.staff = []
    n = 0
    for s in config.SITES:
        roles = [r for r in config.ESCALATION if r != '안전요원' or s['id'] in config.LIFEGUARD_SITES] + ['팀장']
        for role in roles:
            state.staff.append({'site': s['id'], 'role': role, 'name': sur[n % len(sur)] + 'OO',
                                'phone': '010-0000-0000', 'status': '대기', 'ts': None,
                                'present': True, 'absence': ''})
            n += 1
    for role, title, phone in config.HQ_STAFF:
        state.staff.append({'site': None, 'role': role, 'title': title, 'name': 'OOO',
                            'phone': phone, 'status': '대기', 'ts': None, 'present': True, 'absence': ''})
    for i, p in enumerate(state.staff):
        p['id'] = i
    # 기본 근무표: 평일 근무·주말 휴무, 현장 담당자·안전요원은 주말 근무 + 평일 하루 휴무. 오늘은 전원 근무
    rnd = random.Random(7)
    today = time.localtime(now()).tm_wday
    for p in state.staff:
        week = ['근무'] * 5 + ['휴무', '휴무']
        if p['site'] and p['role'] in ('현장 담당자', '안전요원'):
            week[rnd.randrange(5)] = '휴무'
            week[5] = week[6] = '근무'
        week[today] = '근무'
        p['week'] = week
    _apply_absences(today)

    state.incidents, state._seq = [], 0
    state.broadcasts = []
    _seed_history()
    _seed_today()
    state.selected_incident = state.selected_site = None
    touch()


# ── 표시용 도우미 ──
def md_hm(t):
    return time.strftime('%m.%d %H:%M', time.localtime(t))


def hm(t):
    return time.strftime('%H:%M', time.localtime(t))


def ago(t):
    m = int((now() - t) // 60)
    return f'{m // 60}시간 {m % 60}분' if m >= 60 else f'{m}분'


load_scenario()
reset_sample()