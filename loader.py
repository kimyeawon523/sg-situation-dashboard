"""data/scenario.xlsx 읽기. 파일이 없거나 비어 있어도 서버는 켜지고, 확인할 점은 터미널에 출력한다.
시트: 상황유형 · 체크리스트 · 금일 상황 · 전일 기록 · 사업장 상태 · 인력 부재"""
import datetime as dt

import config

SITE_ID = {s['name']: s['id'] for s in config.SITES}
SITE_LINKED = {s['id']: s['linked'] for s in config.SITES}
GRADE_NAMES = [g['name'] for g in config.GRADES]
FIRST_ROW = 5   # 3행 제목, 4행 예시

STEPS = list(config.STAGES) + ['오경보 종결']                 # 금일 상황 처리 단계
SITE_KINDS = ['보고 지연', '이상 보고', '정상 보고', '보조설비 이상', '연결 끊김', '연결 복구']
REPORT_KINDS = ('보고 지연', '이상 보고', '정상 보고')         # 미연계 사업장만
LINK_KINDS = ('연결 끊김', '연결 복구')                       # AI·경보 연계 사업장만
ROLES = list(config.ESCALATION) + ['팀장']
HQ = '공단 본부'
HQ_TITLES = [t for _, t, _ in config.HQ_STAFF]                 # 공단 본부 직위 (재난안전실장 등)
DAYS = ['월', '화', '수', '목', '금', '토', '일']


def _rows(ws, ncol):
    """빈 행과 (예시) 행을 건너뛰고 (행 번호, 값 목록)을 돌려줌"""
    for r, row in enumerate(ws.iter_rows(min_row=FIRST_ROW, max_col=ncol, values_only=True), FIRST_ROW):
        vals = [v.strip() if isinstance(v, str) else v for v in row]
        vals = [None if v == '' else v for v in vals]
        vals += [None] * (ncol - len(vals))
        if all(v is None for v in vals):
            continue
        if any(isinstance(v, str) and v.startswith('(예시)') for v in vals):
            continue
        yield r, vals


def _num(v):
    """숫자 칸 → float (비었거나 숫자가 아니면 None)"""
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _hm(v):
    """시각 칸 → 자정부터의 분 (hh:mm 글자·시각 값 모두 허용, 없으면 None)"""
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        v = v.time()
    if isinstance(v, dt.time):
        return v.hour * 60 + v.minute
    if isinstance(v, (int, float)):          # 엑셀 시각 숫자(하루 = 1)
        return round(float(v) * 1440) % 1440
    try:
        h, m = str(v).split(':')[:2]
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def _sheet(wb, name, warn):
    if name in wb.sheetnames:
        return wb[name]
    warn(f'시트 없음: {name} (시트 이름을 바꾸지 않았는지 확인)')
    return None


def _incident(where, vals, types, warn):
    """금일 상황·전일 기록 공통 앞 7열 검증 → dict 또는 None"""
    site, loc, tname, grade, entry, desc = vals
    if site not in SITE_ID:
        warn(f'{where}: 사업장 "{site}" 확인 필요')
        return None
    if tname not in types:
        warn(f'{where}: 상황유형에 없는 유형명 "{tname}"')
        return None
    if grade and grade not in GRADE_NAMES:
        warn(f'{where}: 등급 "{grade}" 확인 필요 → 기본 등급 사용')
        grade = None
    if entry not in config.ENTRY_ROUTES:
        warn(f'{where}: 접수 경로 "{entry}" 확인 필요')
        return None
    return {'site': SITE_ID[site], 'loc': loc or types[tname]['loc'], 'type': tname,
            'grade': grade or types[tname]['grade'], 'entry': entry, 'desc': desc or ''}


def _report(vals):
    handler, loc_detail, damage, result, cause, memo = vals
    return {'handler': handler or '', 'loc_detail': loc_detail or '', 'damage': damage or '',
            'result': result or '', 'cause': cause or '', 'memo': memo or ''}


REPORT_NEED = {'handler': '담당자', 'loc_detail': '세부 위치', 'damage': '피해 내용', 'result': '조치 결과'}


def load(path=config.SCENARIO_FILE):
    out = {'types': {}, 'checklists': {}, 'today': [], 'yesterday': [], 'site_events': [],
           'absences': [], 'warnings': []}
    warn = out['warnings'].append
    if not path.exists():
        warn(f'파일 없음: {path}')
        return out
    try:
        import openpyxl
    except ImportError:
        warn('openpyxl 미설치 → 터미널에서 pip install openpyxl')
        return out

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        # ── 상황유형: 유형명, 분류, 기본 등급, 주요 발생 위치, 설명 ──
        types = out['types']
        ws = _sheet(wb, '상황유형', warn)
        for r, (name, cat, grade, loc, desc) in (_rows(ws, 5) if ws else []):
            where = f'상황유형 {r}행'
            if not name:
                warn(f'{where}: 유형명 없음')
                continue
            if cat not in config.CATEGORIES:
                warn(f'{where}: 분류 "{cat}" 확인 필요')
                continue
            if grade not in GRADE_NAMES:
                warn(f'{where}: 기본 등급 "{grade}" 확인 필요')
                continue
            if name in types:
                warn(f'{where}: 유형명 "{name}" 중복 → 아래 행으로 덮어씀')
            types[name] = {'category': cat, 'grade': grade, 'loc': loc or '', 'desc': desc or ''}

        # ── 체크리스트: 유형명, 순서, 구분, 조치 내용, 근거 ──
        ws = _sheet(wb, '체크리스트', warn)
        for r, (tname, order, kind, text, basis) in (_rows(ws, 5) if ws else []):
            where = f'체크리스트 {r}행'
            if tname not in types:
                warn(f'{where}: 상황유형에 없는 유형명 "{tname}"')
                continue
            if not text:
                warn(f'{where}: 조치 내용 없음')
                continue
            out['checklists'].setdefault(tname, []).append({
                'order': order if isinstance(order, (int, float)) else 99,
                'kind': kind or '', 'text': text, 'basis': basis or ''})
        for items in out['checklists'].values():
            items.sort(key=lambda x: x['order'])

        # ── 금일 상황: 접수(분 전) … 영상 파일, 처리 단계, 시각 4개(분 전), 보고서 6개 ──
        ws = _sheet(wb, '금일 상황', warn)
        for r, v in (_rows(ws, 19) if ws else []):
            where = f'금일 상황 {r}행'
            ago = _num(v[0])
            if ago is None or ago < 0:
                warn(f'{where}: 접수(분 전) "{v[0]}"이 0 이상 숫자가 아님')
                continue
            inc = _incident(where, v[1:7], types, warn)
            if not inc:
                continue
            step = v[8] or None
            if step and step not in STEPS:
                warn(f'{where}: 처리 단계 "{step}" 확인 필요 → 접수로 읽음')
                step = None
            rep = _report(v[13:19])
            if step == config.DONE_STAGE:
                miss = [label for k, label in REPORT_NEED.items() if not rep[k]]
                if miss:
                    warn(f'{where}: 보고 완료인데 {"·".join(miss)} 없음')
            inc.update(ago=ago, video=v[7] or '', step=step,
                       call=_num(v[9]), resp=_num(v[10]), action=_num(v[11]), close=_num(v[12]), rep=rep)
            out['today'].append(inc)
        out['today'].sort(key=lambda e: -e['ago'])                  # 오래된 접수부터

        # ── 전일 기록: 접수 시각 … 상황 설명, 시각 4개(hh:mm), 보고서 6개 ──
        ws = _sheet(wb, '전일 기록', warn)
        for r, v in (_rows(ws, 17) if ws else []):
            where = f'전일 기록 {r}행'
            start = _hm(v[0])
            if start is None:
                warn(f'{where}: 접수 시각 "{v[0]}" 확인 필요 (hh:mm)')
                continue
            inc = _incident(where, v[1:7], types, warn)
            if not inc:
                continue
            action, close = _hm(v[9]), _hm(v[10])
            rep = _report(v[11:17])
            miss = [label for k, label in REPORT_NEED.items() if not rep[k]]
            if action is None or close is None:
                miss = ['조치 완료 시각' if action is None else '', '종결 시각' if close is None else ''] + miss
            miss = [m for m in miss if m]
            if miss:
                warn(f'{where}: {"·".join(miss)} 없음')
            inc.update(start_min=start, call=_hm(v[7]), resp=_hm(v[8]), action=action, close=close, rep=rep)
            out['yesterday'].append(inc)
        out['yesterday'].sort(key=lambda e: e['start_min'])

        # ── 사업장 상태: 발생(분 전), 사업장, 종류, 내용 ──
        ws = _sheet(wb, '사업장 상태', warn)
        for r, (ago, site, kind, note) in (_rows(ws, 4) if ws else []):
            where = f'사업장 상태 {r}행'
            if site not in SITE_ID:
                warn(f'{where}: 사업장 "{site}" 확인 필요')
                continue
            sid = SITE_ID[site]
            if kind not in SITE_KINDS:
                warn(f'{where}: 종류 "{kind}" 확인 필요')
                continue
            if kind in REPORT_KINDS and SITE_LINKED[sid]:
                warn(f'{where}: {site}는 AI·경보 연계 사업장이라 "{kind}"를 쓸 수 없음')
                continue
            if kind in LINK_KINDS and not SITE_LINKED[sid]:
                warn(f'{where}: {site}는 미연계 사업장이라 "{kind}"를 쓸 수 없음')
                continue
            if kind == '보고 지연' and note is not None and _num(note) is None:
                warn(f'{where}: 보고 지연 내용 "{note}"이 숫자(분)가 아님 → 기준 시간 사용')
                note = None
            out['site_events'].append({'ago': _num(ago) or 0, 'site': sid, 'kind': kind,
                                       'note': '' if note is None else str(note)})
        out['site_events'].sort(key=lambda e: -e['ago'])

        # ── 인력 부재: 사업장, 역할, 요일, 사유 ──
        ws = _sheet(wb, '인력 부재', warn)
        for r, (site, role, day, reason) in (_rows(ws, 4) if ws else []):
            where = f'인력 부재 {r}행'
            if site != HQ and site not in SITE_ID:
                warn(f'{where}: 사업장 "{site}" 확인 필요')
                continue
            if role not in (HQ_TITLES if site == HQ else ROLES):
                warn(f'{where}: {"직위" if site == HQ else "역할"} "{role}" 확인 필요')
                continue
            if day != '오늘' and day not in DAYS:
                warn(f'{where}: 요일 "{day}" 확인 필요')
                continue
            if reason not in config.ABSENCE_REASONS:
                warn(f'{where}: 사유 "{reason}" 확인 필요')
                continue
            out['absences'].append({'site': None if site == HQ else SITE_ID[site], 'role': role, 'day': day, 'reason': reason})
    finally:
        wb.close()
    return out


def load_facilities(path=config.FACILITY_FILE):
    """data/facilities.xlsx 읽기. 사업단별 시트: 사업장명, 중요설비, 중점관리사항, 비고
    - 사업장명이 비어 있으면(병합 칸) 위 행 사업장명으로 이어서 읽음
    - 중요설비 한 칸에 여러 개가 있으면 줄바꿈·쉼표로 나눔
    - 관할 범위 밖(검단구) 사업장은 건너뜀"""
    out = {'facilities': {}, 'warnings': []}
    warn = out['warnings'].append
    if not path.exists():
        warn(f'파일 없음: {path}')
        return out
    try:
        import openpyxl
    except ImportError:
        warn('openpyxl 미설치 → 터미널에서 pip install openpyxl')
        return out

    all_id = {s['name']: s['id'] for s in getattr(config, 'ALL_SITES', config.SITES)}
    scope = {s['id'] for s in config.SITES}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            if ws.title == '작성안내':
                continue
            last = None
            for r, (name, equip, focus, note) in _rows(ws, 4):
                where = f'{ws.title} {r}행'
                name = name or last
                last = name
                if name not in all_id:
                    warn(f'{where}: 사업장 "{name}" 이름이 config.py와 다름')
                    continue
                sid = all_id[name]
                if sid not in scope:
                    continue
                if not equip:
                    warn(f'{where}: 중요설비 없음')
                    continue
                names = [x.strip() for part in str(equip).splitlines()
                         for x in part.split(',') if x.strip()]
                out['facilities'].setdefault(sid, []).append(
                    {'names': names, 'focus': str(focus or ''), 'note': str(note or '')})
    finally:
        wb.close()
    return out