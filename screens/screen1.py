"""화면1 · 긴급·미조치 알림 (v5.2) — 관제사 기본 화면
제목줄: 금일 접수 · 조치 완료율 · 관제사 · 시계
위: 지금 처리할 상황 카드 (긴급 이상 미조치 + 미응답 호출) / 가운데: 상황목록 / 아래: 운영 지표 카드 3개
오른쪽 끝: 내부 채팅방 (마우스를 대면 열림) — 상황일지의 호출·응답·신고·메모를 대화 형태로 표시 + 전체 전파
카드·목록·말풍선 클릭 → 오른쪽 슬라이드 카드 2장(처리 · 접수 내역·상황일지)
처리 입력은 이 화면 한 곳에서 하고, 화면2~5는 선택된 상황에 맞춰 표시만 한다."""
import csv
import io
import time
from datetime import datetime

from nicegui import ui

import config
import state as S
from screens import screen_root, header, live, clock, grade, grade_html, step_html, T, C, B

URGENT = '긴급 이상 미조치'
CAT_TABS = [('전체', 'list'), ('안전사고', 'personal_injury'), ('보안', 'shield'),
            ('시설장애', 'construction'), ('기상·재난', 'thunderstorm')]
HEADS = ['위험등급', '사업장', '상황유형', '발생위치', '발생시각', '경과', '처리단계', '반복']
ELAPSED_ALERT_MIN = {'재난': 10, '긴급': 10, '주의': 60, '알림': 120}   # 경과시간 빨강 표시 기준(분)
CAT_COLOR = {'안전사고': C['alarm'], '보안': '#7C5CC4', '시설장애': C['warn'], '기상·재난': B['sky']}
KIND_COLOR = {'확인': B['blue'], '전파': C['warn'], '지시': C['ok'], '기록': '#6B7280'}
OPT_GRADE_COLOR = {'재난': '#8B0A1A', '긴급': '#E5383B', '주의': '#F08C00', '알림': '#C99A00'}
NEXT_ACTION = {
    '접수': '상황 확인 후 사업장 담당자 호출 · 위급 시 119 신고',
    '사업장 통보': '담당자 응답 대기 · 미응답·부재 시 차순위 호출',
    '현장 확인': '현장 조치 진행 확인 · 조치 내용 상황일지 기록',
    '조치 완료': '보고서 작성 후 종결',
    '보고 완료': '종결된 상황',
}
CALL_COLOR = {'미호출': T['muted'], '호출 중': '#9A7600', '미응답': C['alarm'],
              '응답': C['ok'], '신고 완료': C['ok'], '통보 완료': C['ok']}
HQ_ROLES = ['재난안전상황실', '경영진']             # 공단 상급 보고 (팀장은 사업장 지정에서 선택)
SITE_ROLE_NAME = {'팀장': '소관 팀장'}
MEMBERS = [('관제사', B['blue']), ('사업장 담당자', C['ok']), ('당직자', '#7C5CC4'),
           ('팀장', C['warn']), ('재난안전실', C['alarm']), ('경영진', '#4B5563')]
REPORT_FIELDS = [('handler', '담당자 이름 *', False), ('loc_detail', '세부 위치 *', False),
                 ('damage', '피해 내용 *', True), ('result', '조치 결과 *', True), ('cause', '원인 (선택)', True)]

CSS = f"""
<style>
/* ===== 제목줄 요약 ===== */
.s1-sum {{ display:flex; align-items:baseline; gap:8px; font-size:19px; color:{T['muted']}; white-space:nowrap; }}
.s1-sum b {{ font-size:28px; font-weight:700; color:{T['text']}; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; }}
.s1-sum .d {{ font-size:16px; }}
.s1-num {{ font-variant-numeric:tabular-nums; }}

/* ===== 배치 공통 ===== */
.s1-mainc {{ flex:1; min-height:0; display:flex; flex-direction:column; gap:20px; }}
.s1-panel {{ padding:22px 26px; flex-shrink:0; }}
.s1-ph {{ display:flex; align-items:center; gap:10px; font-size:22px; font-weight:650; }}
.s1-ph .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:42px; height:42px;
                 border-radius:13px; background:{B['blue']}12; font-size:23px; color:{B['blue']}; }}
.s1-ph .r {{ margin-left:auto; font-size:16px; font-weight:400; color:{T['muted']}; }}
@keyframes s1-pulse {{ 0%, 100% {{ opacity:1; }} 50% {{ opacity:.45; }} }}

/* ===== 위: 지금 처리할 상황 ===== */
.s1-hl {{ display:flex; align-items:center; gap:16px; }}
.s1-hl-t {{ font-size:32px; font-weight:700; letter-spacing:-0.02em; }}
.s1-hl-t b {{ color:{C['alarm']}; }}
.s1-hl-s {{ font-size:17px; color:{T['muted']}; }}
.s1-strip {{ display:flex; gap:16px; overflow-x:auto; padding:8px 4px 12px; margin-top:14px; }}
.s1-icard {{ flex:0 0 500px; display:flex; flex-direction:column; gap:10px; padding:20px 22px; border-radius:22px;
            background:{T['panel']}; box-shadow:inset 0 0 0 1.5px #E8EBEF; cursor:pointer;
            transition:transform .25s var(--sg-ease), box-shadow .25s var(--sg-ease); }}
.s1-icard:hover {{ transform:translateY(-3px); box-shadow:inset 0 0 0 1.5px #E8EBEF, var(--sg-shadow-up); }}
.s1-icard.high {{ background:linear-gradient(180deg, #FFF4F4 0%, #FFFFFF 65%); box-shadow:inset 0 0 0 2px #E5383B55; }}
.s1-icard.flash {{ animation:s1-cflash 1.8s ease-in-out infinite; }}
@keyframes s1-cflash {{ 0%, 100% {{ background:#FFF4F4; }} 50% {{ background:#FDE2E2; }} }}
.s1-icard.on {{ box-shadow:0 0 0 3px {B['blue']}, var(--sg-shadow-up); }}
.s1-ic-top {{ display:flex; align-items:center; gap:10px; font-size:16px; color:{T['muted']}; }}
.s1-ic-t {{ font-size:25px; font-weight:700; letter-spacing:-0.01em; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s1-ic-d {{ font-size:16px; color:{T['muted']}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s1-ic-step {{ display:flex; align-items:center; gap:10px; font-size:15px; color:{T['muted']}; }}
.s1-ic-foot {{ display:flex; align-items:center; gap:10px; padding-top:12px; border-top:1px dashed #E3E7EC; }}
.s1-ic-call {{ display:inline-flex; align-items:center; gap:6px; font-size:16px; font-weight:650; }}
.s1-ic-el {{ margin-left:auto; font-size:19px; font-weight:650; font-variant-numeric:tabular-nums; }}

/* ===== 가운데: 상황목록 ===== */
.s1-listp {{ flex:1; min-height:0; display:flex; flex-direction:column; padding:20px 18px 12px; }}
.s1-listhead {{ display:flex; align-items:center; gap:10px; padding:0 8px 12px; flex-shrink:0; }}
.s1-listhead .t {{ font-size:24px; font-weight:650; margin-right:8px; }}
.s1-kp {{ display:inline-flex; align-items:center; gap:10px; padding:9px 18px; border-radius:999px;
         background:var(--sg-soft); font-size:18px; font-weight:600; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s1-kp b {{ font-size:22px; font-weight:700; }}
.s1-kp:hover {{ background:#E9ECF0; }}
.s1-kp.on {{ box-shadow:0 0 0 3px {B['blue']}66; }}
.s1-kp.urgent {{ background:linear-gradient(135deg, #F25A5C, {C['alarm']}); color:#fff; box-shadow:0 6px 18px rgba(229,56,59,.28); }}
.s1-kp.urgent b {{ animation:s1-pulse 1.8s ease-in-out infinite; }}
.s1-kp.urgent.on {{ box-shadow:0 0 0 4px rgba(139,10,26,.35), 0 6px 18px rgba(229,56,59,.28); }}
.s1-tablebox {{ flex:1; min-height:0; overflow-y:auto; padding:0 6px; }}
.s1-row {{ position:relative; display:grid; grid-template-columns:120px 1.6fr 1.6fr 1.1fr 1fr .8fr 1.3fr 70px;
          align-items:center; gap:16px; padding:14px 22px; border-radius:18px; font-size:20px;
          transition:background .2s var(--sg-ease); }}
.s1-row > * {{ min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.s1-row.head {{ position:sticky; top:0; z-index:2; background:{T['panel']}; border-radius:0; padding-top:10px;
               padding-bottom:12px; font-size:16px; font-weight:600; color:{T['muted']}; box-shadow:inset 0 -2px 0 #E3E7EC; }}
.s1-row.item {{ cursor:pointer; margin-top:2px; }}
.s1-row.item + .s1-row.item::before {{ content:''; position:absolute; left:22px; right:22px; top:-2px; height:1px;
                                      background:#E4E8ED; transition:opacity .2s; }}
.s1-row.item:hover::before, .s1-row.item:hover + .s1-row.item::before,
.s1-row.item.on::before, .s1-row.item.on + .s1-row.item::before {{ opacity:0; }}
.s1-row.item:hover {{ background:var(--sg-soft); }}
.s1-row.item.on {{ background:{B['blue']}10; box-shadow:inset 0 0 0 2px {B['blue']}30; }}
.s1-row.flash {{ animation:s1-flash 1.8s ease-in-out infinite; }}
@keyframes s1-flash {{ 0%, 100% {{ background:transparent; }} 50% {{ background:#E5383B16; }} }}
.s1-row.item > :nth-child(2), .s1-row.item > :nth-child(3) {{ font-size:23px; font-weight:650; color:{T['text']}; }}
.s1-row .sg-sub {{ font-size:15px; font-weight:400; margin-top:3px; }}
.s1-when b {{ font-size:21px; font-weight:700; font-variant-numeric:tabular-nums; }}
.s1-when span {{ display:block; font-size:15px; color:{T['muted']}; margin-top:3px; }}
.s1-el {{ font-size:20px; font-weight:600; font-variant-numeric:tabular-nums; }}
.s1-el.over {{ color:#D62F32; font-weight:700; }}
.s1-stage {{ display:flex; align-items:center; gap:12px; }}
.s1-stage span {{ font-size:20px; font-weight:600; color:{T['text']}; }}
.s1-rep {{ font-size:20px; font-weight:600; font-variant-numeric:tabular-nums; }}
.s1-empty {{ padding:24px; font-size:19px; color:{T['muted']}; }}

/* ===== 아래: 운영 지표 ===== */
.s1-mets {{ display:grid; grid-template-columns:1.25fr 1fr 1fr; gap:20px; flex-shrink:0; }}
.s1-mets .s1-panel {{ display:flex; flex-direction:column; }}
.s1-rate {{ display:flex; align-items:center; gap:30px; margin-top:16px; }}
.s1-rate svg {{ width:150px; height:150px; flex-shrink:0; }}
.s1-rate-rows {{ flex:1; display:flex; flex-direction:column; gap:18px; }}
.s1-rr {{ display:grid; grid-template-columns:130px 1fr 60px 52px; align-items:center; gap:12px; font-size:17px; }}
.s1-rr .l {{ display:flex; align-items:center; gap:8px; font-weight:600; }}
.s1-rr .l i {{ width:12px; height:12px; border-radius:4px; }}
.s1-rr b {{ text-align:right; font-weight:700; font-variant-numeric:tabular-nums; }}
.s1-rr .p {{ text-align:right; font-size:15px; color:{T['muted']}; font-variant-numeric:tabular-nums; }}
.s1-bar-t {{ height:14px; border-radius:999px; background:#EDF0F3; overflow:hidden; }}
.s1-bar-t i {{ display:block; height:100%; border-radius:999px; }}
.s1-bars {{ display:flex; flex-direction:column; gap:14px; margin-top:18px; }}
.s1-bar {{ display:grid; grid-template-columns:96px 1fr 40px; align-items:center; gap:12px; font-size:17px; }}
.s1-bar b {{ text-align:right; font-variant-numeric:tabular-nums; }}
.s1-top3 {{ display:flex; flex-direction:column; gap:10px; margin-top:14px; }}
.s1-rank {{ display:flex; align-items:center; gap:12px; padding:10px 14px; border-radius:14px; background:var(--sg-soft); font-size:17px; }}
.s1-rank .no {{ width:30px; height:30px; border-radius:50%; background:#fff; display:flex; align-items:center;
               justify-content:center; font-weight:700; color:{B['blue']}; flex-shrink:0; }}

/* ===== 오른쪽 끝: 내부 채팅방 (80% 고정 크기, 마우스를 대면 열림) ===== */
.s1-chat-zone {{ position:fixed; right:0; top:0; width:12px; height:var(--sg-nav-h, 100vh); z-index:3000;
                zoom:var(--sg-nav-zoom, 1); }}
.s1-chat-handle {{ position:fixed; right:0; top:60%; z-index:2999; zoom:var(--sg-nav-zoom, 1);
                  display:flex; flex-direction:column; align-items:center; gap:8px; padding:16px 10px;
                  border-radius:16px 0 0 16px; background:linear-gradient(180deg, {B['sky']}, {B['blue']}); color:#fff;
                  font-size:15px; font-weight:600; writing-mode:vertical-rl; cursor:pointer;
                  box-shadow:-4px 4px 16px rgba(39,131,197,.30); }}
.s1-chat-handle .q-icon {{ font-size:22px; writing-mode:horizontal-tb; }}
.s1-unread {{ writing-mode:horizontal-tb; min-width:22px; height:22px; padding:0 6px; border-radius:999px;
             background:{C['alarm']}; color:#fff; font-size:12px; font-weight:700; display:flex; align-items:center;
             justify-content:center; box-shadow:0 0 0 2px #fff; }}
.s1-chat {{ position:fixed; right:0; top:0; width:470px; height:var(--sg-nav-h, 100vh); z-index:3001;
           zoom:var(--sg-nav-zoom, 1); display:flex; flex-direction:column; background:{T['panel']};
           border-radius:24px 0 0 24px; box-shadow:-10px 0 40px rgba(16,24,40,.16); overflow:hidden;
           transform:translateX(105%); transition:transform .3s var(--sg-ease) .2s; }}
.s1-chat-zone:hover ~ .s1-chat, .s1-chat-handle:hover ~ .s1-chat {{ transform:translateX(0); transition-delay:.3s; }}
.s1-chat:hover, .s1-chat:focus-within {{ transform:translateX(0); transition-delay:0s; }}
.s1-chat-head {{ padding:22px 22px 14px; border-bottom:1px solid #EEF0F3; flex-shrink:0; }}
.s1-chat-t {{ display:flex; align-items:center; gap:8px; font-size:19px; font-weight:700; }}
.s1-chat-t .q-icon {{ font-size:22px; color:{B['blue']}; }}
.s1-chat-s {{ font-size:13px; color:{T['muted']}; margin-top:4px; }}
.s1-members {{ display:flex; align-items:center; margin-top:12px; }}
.s1-mem {{ width:32px; height:32px; border-radius:50%; border:2px solid #fff; margin-left:-8px; display:flex;
          align-items:center; justify-content:center; font-size:12px; font-weight:700; color:#fff; background:var(--c); }}
.s1-mem:first-child {{ margin-left:0; }}
.s1-members span {{ margin-left:10px; font-size:13px; color:{T['muted']}; }}
.s1-pins {{ display:flex; flex-direction:column; gap:6px; padding:10px 16px 0; flex-shrink:0; }}
.s1-pin {{ display:flex; align-items:center; gap:8px; padding:9px 12px; border-radius:12px; background:#FDECEC;
          color:#D62F32; font-size:13px; font-weight:650; cursor:pointer; }}
.s1-pin .q-icon {{ font-size:18px; }}
.s1-feed {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column-reverse; gap:12px;
           padding:14px 16px; background:#F7F9FB; margin-top:10px; }}
.s1-msg {{ display:flex; gap:8px; align-items:flex-start; }}
.s1-msg .av {{ width:32px; height:32px; border-radius:50%; flex-shrink:0; display:flex; align-items:center;
              justify-content:center; background:var(--c); color:#fff; font-size:13px; font-weight:700; }}
.s1-msg .av .q-icon {{ font-size:18px; }}
.s1-msg .bd {{ max-width:82%; display:flex; flex-direction:column; }}
.s1-msg .who {{ font-size:12px; color:{T['muted']}; margin-bottom:3px; }}
.s1-msg .bb {{ padding:9px 13px; border-radius:4px 14px 14px 14px; background:#fff; font-size:14px; line-height:1.45;
              cursor:pointer; box-shadow:0 1px 2px rgba(16,24,40,.06); }}
.s1-msg.me {{ flex-direction:row-reverse; }}
.s1-msg.me .bd {{ align-items:flex-end; }}
.s1-msg.me .bb {{ border-radius:14px 4px 14px 14px; background:{B['blue']}; color:#fff; }}
.s1-msg.cast .bb {{ background:linear-gradient(135deg, {B['sky']}, {B['blue']}); }}
.s1-alertmsg {{ padding:10px 13px; border-radius:14px; background:#fff; font-size:14px; line-height:1.5; cursor:pointer;
               box-shadow:inset 0 0 0 1.5px color-mix(in srgb, var(--c) 40%, transparent); }}
.s1-alertmsg b {{ color:var(--c); }}
.s1-alertmsg .t {{ float:right; font-size:12px; color:{T['muted']}; }}
.s1-sys {{ align-self:center; font-size:12px; color:{T['muted']}; padding:3px 10px; border-radius:999px; background:#EEF1F4; }}
.s1-compose {{ display:flex; flex-direction:column; gap:10px; padding:12px 16px 18px; border-top:1px solid #EEF0F3; flex-shrink:0; }}
.s1-to {{ display:flex; align-items:center; flex-wrap:wrap; gap:6px; }}
.s1-to .l {{ font-size:13px; font-weight:700; color:{T['muted']}; margin-right:4px; }}
.s1-tp {{ padding:5px 12px; border-radius:999px; background:var(--sg-soft); font-size:13px; font-weight:600;
         color:{T['muted']}; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s1-tp:hover {{ background:#E9ECF0; }}
.s1-tp.on {{ background:{B['blue']}; color:#fff; }}
.s1-tp.sub.on {{ background:{B['blue']}14; color:{B['blue']}; box-shadow:inset 0 0 0 1.5px {B['blue']}; }}
.s1-tsel {{ display:inline-flex; align-items:center; gap:4px; padding:4px 10px; border-radius:999px; font-size:13px;
           font-weight:600; color:{B['blue']}; background:{B['blue']}14; cursor:pointer; }}
.s1-tsel .q-icon {{ font-size:14px; }}
.s1-to-sum {{ font-size:12px; color:{T['muted']}; }}
.s1-to-sum b {{ color:{B['blue']}; }}
.s1-send-row {{ display:flex; align-items:center; gap:8px; }}
.s1-hits {{ display:flex; flex-direction:column; gap:2px; padding:4px; border-radius:12px; background:var(--sg-soft); }}
.s1-hit {{ display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 12px; border-radius:10px;
          font-size:13px; font-weight:600; cursor:pointer; }}
.s1-hit:hover {{ background:#fff; }}
.s1-hit span {{ font-size:12px; font-weight:400; color:{T['muted']}; }}
.s1-sitecard {{ display:flex; flex-direction:column; gap:8px; padding:10px 12px; border-radius:12px; background:{B['blue']}0D; }}
.s1-sitecard .nm {{ display:flex; align-items:center; font-size:14px; font-weight:700; }}

/* ===== 상황 등록 창 ===== */
.s1-reg {{ width:1560px; max-width:none !important; padding:36px 40px !important; gap:24px !important;
          border-radius:28px !important; }}
.s1-reg-t {{ font-size:34px; font-weight:700; letter-spacing:-0.02em; }}
.s1-reg-body {{ display:grid; grid-template-columns:1fr 1fr; gap:36px; width:100%; }}
.s1-reg-col {{ display:flex; flex-direction:column; gap:22px; min-width:0; }}
.s1-reg-l {{ display:flex; align-items:center; gap:8px; font-size:19px; font-weight:650; color:{T['text']}; margin-bottom:10px; }}
.s1-reg-l .sel {{ margin-left:auto; font-size:17px; font-weight:650; color:{B['blue']}; }}
.s1-reg-l .hint {{ font-size:15px; font-weight:400; color:{T['muted']}; }}
.s1-reg .q-field__native, .s1-reg .q-field__input {{ font-size:21px !important; }}
.s1-reg .q-field--outlined .q-field__control {{ min-height:60px; }}
.s1-sitebox {{ height:600px; overflow-y:auto; margin-top:12px; padding:16px; border-radius:20px; background:var(--sg-soft);
              display:flex; flex-direction:column; gap:18px; }}
.s1-dept {{ font-size:15px; font-weight:650; color:{T['muted']}; margin-bottom:8px; }}
.s1-sites {{ display:flex; flex-wrap:wrap; gap:8px; }}
.s1-site {{ padding:10px 16px; border-radius:14px; background:#fff; font-size:18px; cursor:pointer;
           box-shadow:0 1px 2px rgba(16,24,40,.06); transition:all .2s var(--sg-ease); }}
.s1-site:hover {{ box-shadow:0 0 0 2px {B['blue']}55; }}
.s1-site.on {{ background:{B['blue']}; color:#fff; font-weight:650; box-shadow:0 4px 12px {B['blue']}40; }}
.s1-site .gu {{ font-size:13px; opacity:.65; margin-left:6px; }}
.s1-opts {{ display:flex; flex-wrap:wrap; gap:10px; }}
.s1-opt {{ padding:11px 24px; border-radius:999px; background:var(--sg-soft); font-size:19px; font-weight:600;
          color:{T['muted']}; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s1-opt:hover {{ background:#E9ECF0; }}
.s1-opt.on {{ background:var(--c); color:#fff; box-shadow:0 4px 12px color-mix(in srgb, var(--c) 35%, transparent); }}
.s1-tchips {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
.s1-tchip {{ padding:7px 14px; border-radius:999px; background:var(--sg-soft); font-size:16px; cursor:pointer;
            transition:all .2s var(--sg-ease); }}
.s1-tchip:hover {{ background:#E9ECF0; }}
.s1-tchip.on {{ background:{B['blue']}; color:#fff; }}

/* ===== 슬라이드 상세 ===== */
.s1-ov {{ position:fixed; left:0; top:0; width:100%; height:var(--sg-h, 100vh); z-index:2000; }}
.s1-dim {{ position:absolute; inset:0; background:rgba(17,24,39,.20); backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px); }}
.s1-drawer {{ position:absolute; top:28px; right:28px; bottom:28px; display:flex; gap:22px; }}
.s1-card {{ display:flex; flex-direction:column; min-height:0; overflow:hidden; background:{T['panel']};
           border-radius:28px; box-shadow:0 24px 60px rgba(15,23,42,.18), 0 2px 6px rgba(15,23,42,.06); }}
.s1-card.a {{ width:1180px; }}
.s1-card.b {{ width:760px; }}
.s1-card.a.high {{ box-shadow:0 0 0 3px #E5383B2E, 0 24px 60px rgba(229,56,59,.18), 0 2px 6px rgba(15,23,42,.06); }}
.s1-ov:has(.s1-drawer.anim) .s1-dim {{ animation:s1-fade .3s ease-out both; }}
.s1-drawer.anim .s1-card {{ animation:s1-in .45s var(--sg-ease) both; }}
.s1-drawer.anim .s1-card.b {{ animation-delay:.07s; }}
@keyframes s1-fade {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
@keyframes s1-in {{ from {{ transform:translateX(80px) scale(.98); opacity:0; }} to {{ transform:none; opacity:1; }} }}
.s1-card-head {{ display:flex; align-items:flex-start; gap:12px; padding:30px 34px 10px; flex-shrink:0; }}
.s1-card-head .t {{ font-size:24px; font-weight:650; }}
.s1-card-head .q-btn--round {{ background:var(--sg-soft); }}
.s1-card-body {{ flex:1; min-height:0; overflow-y:auto; padding:0 34px 30px; }}
.s1-dtitle {{ font-size:32px; font-weight:700; letter-spacing:-0.02em; }}
.s1-dsub {{ font-size:18px; color:{T['muted']}; margin-top:6px; }}
.s1-sec {{ padding:22px 0 8px; }}
.s1-sec-title {{ display:flex; align-items:center; gap:10px; font-size:24px; font-weight:650; margin-bottom:16px; }}
.s1-sec-title .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:42px; height:42px;
                        border-radius:12px; background:{B['blue']}12; font-size:23px; color:{B['blue']}; }}
.s1-sec-title .r {{ margin-left:auto; font-size:17px; font-weight:400; color:{T['muted']}; }}
.s1-track {{ display:flex; align-items:flex-start; padding:18px 8px 14px; border-radius:20px; background:var(--sg-soft); }}
.s1-track .st {{ flex:1; position:relative; display:flex; flex-direction:column; align-items:center; gap:10px;
                font-size:18px; color:{T['muted']}; }}
.s1-track .st::before {{ content:''; position:absolute; top:9px; left:-50%; width:100%; height:4px; border-radius:999px; background:#E2E6EB; }}
.s1-track .st:first-child::before {{ display:none; }}
.s1-track .st i {{ width:22px; height:22px; border-radius:50%; background:{T['panel']}; border:4px solid #E2E6EB; z-index:1; }}
.s1-track .st.done {{ color:{T['text']}; }}
.s1-track .st.done i {{ background:var(--c); border-color:var(--c); }}
.s1-track .st.done::before, .s1-track .st.now::before {{ background:var(--c); }}
.s1-track .st.now {{ color:var(--c); font-weight:650; }}
.s1-track .st.now i {{ border-color:var(--c); box-shadow:0 0 0 6px color-mix(in srgb, var(--c) 18%, transparent); }}
.s1-calls {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.s1-call {{ display:flex; align-items:center; gap:14px; padding:18px; border-radius:20px; background:var(--sg-soft); min-width:0;
           transition:transform .25s var(--sg-ease), box-shadow .25s var(--sg-ease), background .25s; }}
.s1-call.click {{ cursor:pointer; }}
.s1-call.click:hover {{ background:{T['panel']}; transform:translateY(-2px); box-shadow:var(--sg-shadow-up); }}
.s1-call.need {{ background:#FDEEEE; }}
.s1-call.need .s1-call-title {{ color:#D62F32; }}
.s1-call .ic {{ width:50px; height:50px; border-radius:16px; background:{T['panel']}; flex-shrink:0;
               display:flex; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(16,24,40,.06); }}
.s1-call .ic .q-icon {{ font-size:26px; }}
.s1-call-title {{ font-size:23px; font-weight:650; }}
.s1-call-sub {{ font-size:17px; color:{T['muted']}; white-space:normal; margin-top:2px; }}
.s1-line {{ display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin-top:12px; padding:16px 22px;
           border-radius:18px; background:var(--sg-soft); font-size:20px; }}
.s1-line .k {{ font-weight:650; }}
.s1-line .q-btn {{ font-size:18px !important; padding:5px 16px !important; }}
.s1-tag {{ padding:5px 14px; border-radius:999px; font-size:17px; font-weight:600; white-space:nowrap;
          color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fff); }}
.s1-checks {{ margin-top:18px; display:flex; flex-direction:column; gap:8px; }}
.s1-check {{ display:flex; align-items:center; gap:16px; padding:16px 20px; border-radius:18px; background:var(--sg-soft); }}
.s1-check.done {{ background:#2EA04310; }}
.s1-no {{ width:40px; height:40px; border-radius:50%; background:{T['panel']}; flex-shrink:0; display:flex; align-items:center;
         justify-content:center; font-size:18px; font-weight:650; color:{B['blue']}; box-shadow:0 1px 3px rgba(16,24,40,.08); }}
.s1-kind {{ padding:4px 14px; border-radius:999px; font-size:16px; font-weight:650; flex-shrink:0;
           color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fff); }}
.s1-check-text {{ font-size:22px; font-weight:600; }}
.s1-check.done .s1-check-text {{ color:{T['muted']}; font-weight:500; }}
.s1-basis {{ font-size:24px !important; color:#B7BEC8; cursor:help; flex-shrink:0; }}
.s1-check-time {{ font-size:19px; font-weight:650; color:{C['ok']}; font-variant-numeric:tabular-nums; }}
.s1-check .q-btn {{ font-size:18px !important; padding:4px 18px !important; }}
.s1-check .q-btn--outline {{ background:{B['blue']}14 !important; color:{B['blue']} !important; }}
.s1-check .q-btn--outline:before {{ border:none; }}
.s1-post-head {{ padding:14px 4px 2px; font-size:16px; color:{T['muted']}; }}
.s1-check.post {{ background:transparent; box-shadow:inset 0 0 0 1.5px #E6E9EE; }}
.s1-check.post .s1-check-text {{ color:{T['muted']}; font-weight:500; }}
.s1-info {{ display:grid; grid-template-columns:120px 1fr; row-gap:14px; column-gap:18px; font-size:20px;
           padding:20px 22px; border-radius:20px; background:var(--sg-soft); }}
.s1-info .k {{ color:{T['muted']}; }}
.s1-tl {{ position:relative; margin-top:18px; padding-left:28px; }}
.s1-tl::before {{ content:''; position:absolute; left:8px; top:10px; bottom:10px; width:2px; border-radius:999px; background:#E8EBEF; }}
.s1-tl-item {{ position:relative; padding:4px 0 16px; }}
.s1-tl-item::before {{ content:''; position:absolute; left:-26px; top:9px; width:14px; height:14px; border-radius:50%;
                      background:#D5DAE1; border:3px solid {T['panel']}; }}
.s1-tl-item.memo::before {{ background:{B['blue']}; box-shadow:0 0 0 4px {B['blue']}22; }}
.s1-tl-text {{ font-size:19px; }}
.s1-tl-item.memo .s1-tl-text {{ font-weight:600; }}
.s1-tl-time {{ font-size:15px; color:{T['muted']}; margin-top:2px; font-variant-numeric:tabular-nums; }}

/* 보고서 작성 */
.s1-report {{ display:flex; flex-direction:column; gap:20px; padding:24px 26px; border-radius:22px;
             background:#F3F9FD; box-shadow:inset 0 0 0 2px {B['blue']}40; }}
.s1-report-hd {{ display:flex; align-items:center; gap:14px; }}
.s1-report-hd .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:52px; height:52px;
                        border-radius:16px; background:{B['blue']}; color:#fff; font-size:30px; }}
.s1-report-hd .t {{ font-size:26px; font-weight:700; color:{B['blue']}; }}
.s1-report-hd .s {{ font-size:17px; color:{T['muted']}; }}
.s1-rgrid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px 18px; }}
.s1-rl {{ font-size:18px; font-weight:650; margin-bottom:8px; }}
.s1-report .q-field__native {{ font-size:20px !important; }}
.s1-report .q-field--outlined .q-field__control {{ background:#fff !important; min-height:56px; }}
.s1-rfoot {{ display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding-top:4px; }}
.s1-rmiss-l {{ font-size:16px; color:{T['muted']}; margin-right:4px; }}

/* ===== 상세 창 가독성 (버튼·알약·보조 글씨 크기 통일) ===== */
.s1-drawer .q-btn {{ font-size:20px !important; font-weight:700; min-height:48px; padding:6px 22px !important;
                    border-radius:14px; }}
.s1-drawer .q-btn .q-icon {{ font-size:24px; }}
.s1-drawer .q-btn--round {{ width:52px; height:52px; min-height:52px; padding:0 !important; border-radius:50%; }}
.s1-drawer .q-btn--round .q-icon {{ font-size:28px; }}
.s1-card-head .q-btn--outline {{ background:#FDECEC !important; }}
.s1-card-head .q-btn--outline:before {{ border:2px solid {C['alarm']}; }}
.s1-card-head {{ align-items:center; }}
.s1-card-head .t {{ font-size:26px; }}
.s1-dtitle {{ font-size:34px; }}
.s1-dsub {{ font-size:20px; }}
.s1-sec-title {{ font-size:26px; }}
.s1-sec-title .r {{ font-size:19px; }}
.s1-track .st {{ font-size:20px; }}
.s1-call-title {{ font-size:24px; }}
.s1-call-sub {{ font-size:19px; }}
.s1-line {{ gap:14px; padding:18px 24px; font-size:22px; }}
.s1-line .sg-muted {{ font-size:19px !important; }}
.s1-tag {{ padding:8px 18px; font-size:19px; font-weight:700; }}
.s1-kind {{ padding:6px 16px; font-size:18px; }}
.s1-no {{ width:44px; height:44px; font-size:20px; }}
.s1-check-text {{ font-size:23px; line-height:1.45; }}
.s1-check-time {{ font-size:20px; }}
.s1-info {{ grid-template-columns:140px 1fr; font-size:22px; }}
.s1-tl-text {{ font-size:21px; }}
.s1-tl-time {{ font-size:17px; }}
!important; border-radius:14px;
                                white-space:nowrap; background:{B['blue']} !important; color:#fff !important; }}

/* 상황일지 조치 메모 입력 */
.s1-memo {{ display:flex; align-items:center; gap:12px; width:100%; }}
.s1-memo-in {{ flex:1; min-width:0; }}
.s1-memo-in .q-field__control {{ height:66px; min-height:66px; padding:0 20px; border-radius:14px !important;
                                background:#fff; box-shadow:inset 0 0 0 1.5px #C9D1DA; }}
.s1-memo-in .q-field__control:before, .s1-memo-in .q-field__control:after {{ display:none !important; }}
.s1-memo-in.q-field--focused .q-field__control {{ box-shadow:inset 0 0 0 2.5px {B['blue']}; }}
.s1-memo-in .q-field__native, .s1-memo-in .q-field__marginal {{ height:66px; min-height:66px; }}
.s1-memo-in .q-field__native {{ font-size:22px !important; }}
.q-btn.s1-memo-btn {{ flex-shrink:0; height:66px; min-height:66px; padding:0 26px !important; border-radius:14px !important;
                     white-space:nowrap; font-size:21px !important; font-weight:700;
                     background:{B['blue']} !important; color:#fff !important; }}
.q-btn.s1-memo-btn .q-icon {{ font-size:26px; margin-right:6px; }}                                

/* ===== 종결 기록 ===== */
.s1-hov {{ z-index:2100; }}
.s1-hist {{ position:absolute; top:28px; bottom:28px; left:50%; transform:translateX(-50%); width:2400px; display:flex;
           background:{T['panel']}; border-radius:28px; overflow:hidden;
           box-shadow:0 24px 60px rgba(15,23,42,.18), 0 2px 6px rgba(15,23,42,.06); animation:s1-fade .3s ease-out both; }}
.s1-hlist {{ width:820px; flex-shrink:0; display:flex; flex-direction:column; background:#F7F9FB; }}
.s1-hhd {{ display:flex; flex-direction:column; gap:16px; padding:30px 28px 16px; }}
.s1-ht {{ display:flex; align-items:center; gap:12px; font-size:30px; font-weight:800; }}
.s1-ht .q-icon {{ font-size:34px; color:{B['blue']}; }}
.s1-ht .n {{ font-size:20px; font-weight:600; color:#4B5563; }}
.s1-hsearch .q-field__control {{ background:#fff !important; border-radius:14px !important; min-height:58px;
                                box-shadow:inset 0 0 0 1.5px #D3D9E0; }}
.s1-hsearch .q-field__native {{ font-size:20px !important; }}
.s1-hitems {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:8px; padding:0 18px 20px; }}
.s1-hi {{ display:flex; flex-direction:column; gap:8px; padding:18px 20px; border-radius:18px; background:#fff; cursor:pointer;
         box-shadow:0 1px 3px rgba(16,24,40,.06); transition:all .2s var(--sg-ease); }}
.s1-hi:hover {{ box-shadow:var(--sg-shadow-up); }}
.s1-hi.on {{ box-shadow:0 0 0 3px {B['blue']}; }}
.s1-hi .top {{ display:flex; align-items:center; gap:10px; }}
.s1-hi .ty {{ flex:1; min-width:0; font-size:23px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s1-hi .tm {{ font-size:18px; color:#4B5563; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.s1-hi .sub {{ font-size:18px; color:#4B5563; }}
.s1-fa {{ padding:3px 12px; border-radius:999px; font-size:16px; font-weight:700; color:#4B5563; background:#E9ECF0; }}
.s1-hbody {{ flex:1; min-width:0; overflow-y:auto; padding:32px 40px; }}
.s1-hempty {{ height:100%; display:flex; align-items:center; justify-content:center; font-size:22px; color:#4B5563; }}
.s1-hstats {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:14px; margin-top:22px; }}
.s1-hstat {{ padding:18px 22px; border-radius:18px; background:var(--sg-soft); }}
.s1-hstat .l {{ font-size:18px; color:#4B5563; }}
.s1-hstat .v {{ font-size:34px; font-weight:800; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; }}
.s1-repv {{ display:grid; grid-template-columns:150px 1fr; row-gap:16px; column-gap:22px; padding:24px 26px;
           border-radius:20px; background:#F3F9FD; font-size:21px; }}
.s1-repv .k {{ color:#4B5563; font-weight:600; }}
.s1-hcheck {{ display:flex; align-items:center; gap:12px; padding:10px 0; font-size:20px; border-bottom:1px solid #F0F2F5; }}
.s1-hcheck .q-icon {{ font-size:26px; }}
.s1-hcheck .t {{ margin-left:auto; font-size:18px; color:#4B5563; font-variant-numeric:tabular-nums; }}

</style>
"""

AUDIO_UNLOCK = """
<script>
document.addEventListener('pointerdown', () => {
  window.sgAudio = window.sgAudio || new (window.AudioContext || window.webkitAudioContext)();
  window.sgAudio.resume();
});
</script>
"""
BEEP_JS = """
(() => { const a = window.sgAudio; if (!a) return;
  [0, 0.3, 0.6].forEach(t => { const o = a.createOscillator(), g = a.createGain();
    o.type = 'square'; o.frequency.value = 880; g.gain.value = 0.12;
    o.connect(g); g.connect(a.destination);
    o.start(a.currentTime + t); o.stop(a.currentTime + t + 0.18); }); })();
"""


# ── 도우미 ──
def delta(cur, prev, unit=''):
    """전일 대비. ▲ 빨강 / ▼ 파랑"""
    d = cur - prev
    if d == 0:
        return '-'
    arrow, color = ('▲', C['alarm']) if d > 0 else ('▼', C['info'])
    return f'<span style="color:{color};font-weight:600">{arrow}{abs(d)}{unit}</span>'


def summary_item(label, value, delta_html):
    ui.html(f'<span class="s1-sum">{label} <b>{value}</b><span class="d">전일 대비 {delta_html}</span></span>')


def operator_chip():
    name, t = S.state.operator, S.state.login_at
    if name and t:
        body = (f'관제사 <b style="color:{B["blue"]}">{name}</b>'
                f'<span class="sg-muted">· 근무 시작 <span class="s1-num">{S.hm(t)}</span> ({S.ago(t)}째)</span>')
    else:
        body = '<span class="sg-muted">관제사 로그인 기록 없음</span>'
    ui.html(f'<span class="sg-chip"><i class="material-icons" style="font-size:24px;color:{B["blue"]}">'
            f'account_circle</i>{body}</span>')


def when_html(ts):
    """발생시각: 시각 크게 + '오늘·어제 · 월.일'"""
    d = datetime.fromtimestamp(ts).date()
    today = datetime.fromtimestamp(S.now()).date()
    day = '오늘' if d == today else '어제' if (today - d).days == 1 else ''
    md = time.strftime('%m.%d', time.localtime(ts))
    return f"<div class='s1-when'><b>{S.hm(ts)}</b><span>{day + ' · ' if day else ''}{md}</span></div>"

def fmt_min(m):
    if m is None:
        return '-'
    return f'{m:.0f}분' if m < 60 else f'{int(m // 60)}시간 {int(m % 60)}분'

def stage_color(inc):
    return C['ok'] if S.needs_report(inc) or S.is_closed(inc) else B['blue']


def elapsed_over(inc):
    return S.is_open(inc) and S.now() - inc['start'] >= ELAPSED_ALERT_MIN.get(inc['grade'], 60) * 60


def tag(text, color):
    ui.html(f'<span class="s1-tag" style="--c:{color}">{text}</span>')


def ph(icon, text, right=''):
    with ui.element('div').classes('s1-ph'):
        ui.icon(icon)
        ui.label(text)
        if right:
            ui.label(right).classes('r')


def sec_title(icon, text, right=''):
    with ui.element('div').classes('s1-sec-title'):
        ui.icon(icon)
        ui.label(text)
        if right:
            ui.label(right).classes('r')


def call_summary(inc):
    """카드 아래 한 줄: (글자, 색, 아이콘) — 현장 호출 진행 상황"""
    if S.needs_report(inc):
        return '보고서 작성 필요', B['blue'], 'edit_note'
    last = None
    for r in S.order_of(inc):
        st, _ = S.call_status(inc, r)
        if st != '미호출':
            last = (r, st)
    if not last:
        return '호출 전 · 담당 호출 필요', (C['alarm'] if S.is_high(inc) else T['muted']), 'call'
    r, st = last
    if st == '미응답':
        return f'{r} 미응답 · 차순위 호출', C['alarm'], 'phone_missed'
    if st == '호출 중':
        return f'{r} 응답 대기', '#9A7600', 'phone_in_talk'
    return f'{r} 응답 · 대응 중', C['ok'], 'check_circle'


def has_no_response(inc):
    return any(S.call_status(inc, r)[0] == '미응답' for r in S.order_of(inc))


def donut_svg(pct, color):
    r = 52
    circ = 2 * 3.14159 * r
    return (f'<svg viewBox="0 0 140 140" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="70" cy="70" r="{r}" fill="none" stroke="#EDF0F3" stroke-width="16"/>'
            f'<circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="16" stroke-linecap="round" '
            f'stroke-dasharray="{circ * pct / 100:.1f} {circ:.1f}" transform="rotate(-90 70 70)"/>'
            f'<text x="70" y="80" text-anchor="middle" font-size="30" font-weight="700" fill="{T["text"]}">{pct}%</text></svg>')


def classify(l):
    """상황일지 한 줄 → 채팅 종류 (None = 제외)"""
    t = l['text']
    if l['kind'] == 'memo':
        return 'memo'
    if t.startswith('체크'):
        return None
    if t.startswith('접수'):
        return 'new'
    if t.startswith('응답'):
        return 'ok'
    if t.startswith(('처리 단계', '보고 완료', '동일', '등급', '영상')):
        return 'sys'
    if '신고' in t:
        return 'report'
    if t.startswith('자동 알람'):
        return 'auto'
    if t.startswith(('호출', '연락')) or t.endswith(('통보', '보고')):
        return 'call'
    return 'sys'


def role_of(text):
    """'호출 · 팀장', '자동 알람 · 당직자 단말' → 역할"""
    if '· ' not in text:
        return ''
    return text.split('· ', 1)[1].split(' 단말')[0].strip()


def staff_name(inc, role):
    p = S.staff_of(inc['site'], role) or next((p for p in S.state.staff if p['role'] == role), None)
    return p['name'] if p else role


def draw():
    ui.add_head_html(CSS + AUDIO_UNLOCK)
    view = {'filter': None, 'detail': None, 'memo': '', 'anim': False, 'seen': 0}
    refs = {}

    # ── 선택·필터 ──
    def set_filter(name):
        view['filter'] = None if name == '전체' or view['filter'] == name else name
        refs['main'].refresh()

    def select(iid):
        view['detail'], view['memo'], view['anim'] = iid, '', True
        S.select_incident(iid)        # 화면2~5에도 해당 상황 표출

    def clear():
        view['detail'], view['memo'] = None, ''
        S.select_incident(None)

    def current():
        for iid in (view['detail'], S.state.selected_incident):
            inc = S.get_incident(iid) if iid else None
            if inc and not S.is_closed(inc):
                return inc
        return None

    def urgent_list():
        return [i for i in S.sorted_incidents() if S.card_of(i) == URGENT]

    # ── 제목줄 오른쪽 ──
    def build_head():
        """미조치 · 점검 필요 사업장(보고 지연 + 연결 끊김) · 기상특보 · 관제사"""
        import weather
        n_open = len(S.open_incidents())
        sites = list(S.state.sites.values())
        n_late = sum(1 for s in sites if S.report_overdue(s))
        n_cut = sum(1 for s in sites if s['linked'] and not s['connected'])
        n_chk = n_late + n_cut
        warns = (getattr(weather, 'data', None) or {}).get('warnings') or []

        def item(label, value, color, sub=''):
            ui.html(f'<span class="s1-sum">{label} <b style="color:{color}">{value}</b>'
                    + (f'<span class="d">{sub}</span>' if sub else '') + '</span>')

        with ui.row().classes('items-center gap-8 no-wrap'):
            item('미조치', f'{n_open}건' if n_open else '이상 없음', C['alarm'] if n_open else C['ok'])
            sub = ' · '.join(x for x in [f'보고 지연 {n_late}' if n_late else '',
                                         f'연결 끊김 {n_cut}' if n_cut else ''] if x)
            item('점검 필요 사업장', f'{n_chk}곳' if n_chk else '없음', '#A85400' if n_chk else C['ok'], sub)
            if warns:
                names = ', '.join(w['kind'] for w in warns[:2]) + (f' 외 {len(warns) - 2}건' if len(warns) > 2 else '')
                item('기상특보', names, C['alarm'])
            else:
                item('기상특보', '없음', T['muted'])
            operator_chip()

    # ── 위: 지금 처리할 상황 카드 ──
    def incident_card(inc, sel):
        site = S.state.sites[inc['site']]
        high = S.is_high(inc) and S.is_open(inc)
        cls = ('s1-icard' + (' high' if high else '') + (' on' if sel and sel['id'] == inc['id'] else '')
               + (' flash' if high and inc['stage'] == config.STAGES[0] else ''))
        card = ui.element('div').classes(cls)
        card.on('click', lambda e, i=inc['id']: select(i))
        text, col, icon = call_summary(inc)
        with card:
            with ui.element('div').classes('s1-ic-top'):
                ui.label(f"{site['name']} · {inc['loc']}") \
                    .style('flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap')
                ui.html(grade_html(inc['grade']))
            ui.label(inc['type']).classes('s1-ic-t')
            ui.label(inc['desc'] or f"{inc['category']} · {inc['entry']}").classes('s1-ic-d')
            with ui.element('div').classes('s1-ic-step'):
                ui.html(step_html(inc['stage']))
                ui.label(inc['stage'])
            with ui.element('div').classes('s1-ic-foot'):
                ui.html(f'<span class="s1-ic-call" style="color:{col}">'
                        f'<i class="material-icons" style="font-size:20px">{icon}</i>{text}</span>')
                ui.label(f"+{S.ago(inc['start'])}").classes('s1-ic-el') \
                    .style(f"color:{'#D62F32' if elapsed_over(inc) else T['text']}")

    def section_urgent(sel):
        hot = [i for i in S.sorted_incidents() if S.is_open(i) and (S.is_high(i) or has_no_response(i))]
        n_urg = len(urgent_list())
        with ui.element('div').classes('sg-panel s1-panel'):
            with ui.element('div').classes('s1-hl'):
                if n_urg:
                    ui.html(f'<div class="s1-hl-t">지금 처리할 긴급 상황이 <b>{n_urg}건</b> 있어요</div>')
                elif hot:
                    ui.html(f'<div class="s1-hl-t">응답이 없는 호출이 <b>{len(hot)}건</b> 있어요</div>')
                else:
                    ui.html('<div class="s1-hl-t">긴급 상황은 없어요</div>')
                ui.label('재난·긴급 미조치 · 미응답 호출 건').classes('s1-hl-s')
            if hot:
                with ui.element('div').classes('s1-strip'):
                    for inc in hot:
                        incident_card(inc, sel)

    # ── 가운데: 상황목록 ──
    def list_row(inc, sel):
        opened = S.is_open(inc)
        site = S.state.sites[inc['site']]
        flash = opened and S.is_high(inc) and inc['stage'] == config.STAGES[0]
        cls = 's1-row item' + (' on' if sel and sel['id'] == inc['id'] else '') + (' flash' if flash else '')
        row = ui.element('div').classes(cls)
        row.on('click', lambda e, i=inc['id']: select(i))
        rep = f"color:{C['alarm']};font-weight:700" if inc['repeat'] >= 2 else ''
        with row:
            ui.html(grade_html(inc['grade']))
            ui.label(site['name'])
            ui.label(inc['type'])
            ui.label(inc['loc'])
            ui.html(when_html(inc['start']))
            ui.html(f"<span class='s1-el{' over' if elapsed_over(inc) else ''}'>"
                    f"{S.ago(inc['start']) if opened else '-'}</span>")
            ui.html(f"<div class='s1-stage'>{step_html(inc['stage'])}<span>{inc['stage']}</span></div>")
            ui.html(f"<span class='s1-rep' style='{rep}'>{inc['repeat']}</span>")

    def section_list(sel):
        all_rows = S.sorted_incidents()
        closed = sum(1 for i in all_rows if S.is_closed(i))
        active = [i for i in all_rows if not S.is_closed(i)]
        counts = {name: len(active) if name == '전체' else sum(1 for i in active if i['category'] == name)
                  for name, _ in CAT_TABS}
        rows = [i for i in active if not view['filter'] or i['category'] == view['filter']]
        with ui.element('div').classes('sg-panel s1-listp'):
            with ui.element('div').classes('s1-listhead'):
                ui.icon('list_alt').classes('sg-ico').style('font-size:28px')
                ui.label('상황목록').classes('t')
                for name, icon in CAT_TABS:
                    on = view['filter'] == name or (name == '전체' and not view['filter'])
                    kp = ui.element('div').classes('s1-kp' + (' on' if on else ''))
                    kp.on('click', lambda e, k=name: set_filter(k))
                    with kp:
                        ui.icon(icon).style('font-size:22px')
                        ui.label(name)
                        ui.html(f'<b>{counts[name]}</b>')
                ui.space()
                ui.label(f'처리 중 {len(active)}건 · 종결 {closed}건').classes('sg-muted').style('font-size:17px;margin-right:8px')
                ui.button(f'종결 기록 {closed}', icon='history', on_click=open_hist).props('unelevated no-caps') \
                    .style(f"background:#EEF1F4 !important;color:{T['text']} !important;font-size:17px;padding:4px 18px")
                ui.button('상황 등록', icon='add', on_click=open_reg).props('unelevated no-caps') \
                    .style(f"background:{B['blue']} !important;color:#fff !important;font-size:17px;padding:4px 18px")
                ui.button('처리 이력 내보내기', icon='download', on_click=export_csv).props('unelevated no-caps') \
                    .style(f"background:{B['blue']}14 !important;color:{B['blue']} !important;font-size:17px;padding:4px 18px")
            with ui.element('div').classes('s1-tablebox'):
                with ui.element('div').classes('s1-row head'):
                    for h in HEADS:
                        ui.label(h)
                for inc in rows:
                    list_row(inc, sel)
                if not rows:
                    ui.label('해당 상황 없음').classes('s1-empty')

    # ── 아래: 운영 지표 ──
    def metrics_panel():
        m = S.ops_metrics()
        sm = S.summary()
        total = sm['today']
        n_open = len(S.open_incidents())
        n_rep = sum(1 for i in S.state.incidents if S.needs_report(i))
        n_done = total - n_open - n_rep
        with ui.element('div').classes('s1-mets'):
            with ui.element('div').classes('sg-panel s1-panel'):
                ph('donut_large', '조치 완료율', f'금일 접수 {total}건 기준')
                with ui.element('div').classes('s1-rate'):
                    ui.html(donut_svg(sm['rate'], C['ok']))
                    with ui.element('div').classes('s1-rate-rows'):
                        for label, n, col in [('종결', n_done, C['ok']), ('보고 미작성', n_rep, B['blue']),
                                              ('미조치', n_open, C['alarm'])]:
                            pct = round(n / total * 100) if total else 0
                            ui.html(f'<div class="s1-rr"><span class="l"><i style="background:{col}"></i>{label}</span>'
                                    f'<div class="s1-bar-t"><i style="width:{pct}%;background:{col}"></i></div>'
                                    f'<b>{n}건</b><span class="p">{pct}%</span></div>')
            with ui.element('div').classes('sg-panel s1-panel'):
                ph('category', '유형별 접수', f'금일 {total}건')
                mx = max(m['by_cat'].values(), default=0) or 1
                with ui.element('div').classes('s1-bars'):
                    for cat, n in m['by_cat'].items():
                        col = CAT_COLOR.get(cat, B['blue'])
                        ui.html(f'<div class="s1-bar"><span>{cat}</span><div class="s1-bar-t">'
                                f'<i style="width:{n / mx * 100:.0f}%;background:{col}"></i></div><b>{n}</b></div>')
            with ui.element('div').classes('sg-panel s1-panel'):
                ph('repeat', '다발 사업장', '반복 포함 접수 횟수')
                with ui.element('div').classes('s1-top3'):
                    if not m['top_sites']:
                        ui.label('접수 없음').classes('sg-muted')
                    for k, (sid, name, n) in enumerate(m['top_sites'], 1):
                        with ui.element('div').classes('s1-rank'):
                            ui.label(str(k)).classes('no')
                            ui.label(name).style('flex:1;font-weight:600')
                            ui.label(f'{n}회').classes('s1-num').style(
                                f"font-weight:700;color:{C['alarm'] if n >= 2 else T['text']}")

    def build_main():
        sel = current()
        with ui.element('div').classes('s1-mainc'):
            section_urgent(sel)
            section_list(sel)
            metrics_panel()

    # ── 오른쪽 끝: 내부 채팅방 ──
    def chat_entries():
        """상황일지 → 채팅 목록. 같은 상황의 신고·보고·연락이 2분 안에 이어지면 말풍선 1개로 묶음"""
        GROUP_SEC = 120
        out = []
        for inc in S.state.incidents:
            for l in inc['log']:
                k = classify(l)
                if k:
                    out.append((l['ts'], k, l, inc))
        for b in S.state.broadcasts:
            out.append((b['ts'], 'cast', b, None))
        out.sort(key=lambda x: x[0])
        merged, last = [], {}
        for ts, k, l, inc in out:
            if k in ('call', 'report') and not l['text'].startswith('호출'):
                g = last.get(inc['id'])
                if g and ts - g['last'] <= GROUP_SEC:
                    g['items'].append(l['text'])
                    g['last'] = ts
                    continue
                g = {'items': [l['text']], 'last': ts}
                last[inc['id']] = g
                merged.append((ts, 'rep', g, inc))
            else:
                if inc and k != 'sys':
                    last.pop(inc['id'], None)          # 다른 대화가 끼면 새 묶음
                merged.append((ts, k, l, inc))
        return merged

    def msg_count():
        return sum(1 for e in chat_entries() if e[1] != 'sys')

    def chat_msg(ts, k, l, inc):
        site = S.state.sites[inc['site']]['name'] if inc else ''
        me_name = S.state.operator or '관제사'
        if k == 'sys':
            ui.label(f"{S.hm(ts)} · {site} {l['text']}").classes('s1-sys')
            return
        if k == 'new':
            col = S.GRADE_COLOR[inc['grade']]
            box = ui.html(f'<div class="s1-alertmsg" style="--c:{col}"><span class="t">{S.hm(ts)}</span>'
                          f'<b>🚨 [{inc["grade"]}] {inc["type"]}</b><br>{site} · {inc["loc"]} · {inc["entry"]} 접수</div>')
            box.on('click', lambda e, i=inc['id']: select(i))
            return
        role = role_of(l.get('text', ''))
        col, av = B['blue'], None
        if k == 'ok':
            me, who, av, col = False, f"{staff_name(inc, role)} · {site} {role}", staff_name(inc, role)[:1], C['ok']
            text = f"{inc['type']} 건 호출 확인했습니다. 현장 확인하겠습니다."
        elif k == 'auto':
            me, who = False, '상황센터 시스템'
            text = f"{site} {inc['loc']} {inc['type']} — {role} {staff_name(inc, role)} 단말로 자동 알람을 보냈습니다."
        elif k == 'call' and l['text'].startswith('호출'):
            me, who = True, me_name
            text = f"@{staff_name(inc, role)} {role}님, {site} {inc['loc']} {inc['type']} 건 현장 확인 부탁드립니다."

        elif k == 'rep':
            me, who = True, me_name
            items = l['items']
            text = (f"{site} {inc['type']} 건 · {items[0]}" if len(items) == 1
                    else f"{site} {inc['type']} 건 · 신고·보고 {len(items)}건 — " + ' / '.join(items))
        
        elif k in ('call', 'report'):
            me, who = True, me_name
            text = f"{site} {inc['type']} 건 · {l['text']}"
        elif k == 'memo':
            me, who = True, l.get('author') or me_name
            text = f"[{site}] {l['text']}"
        else:                                                   # cast
            me, who = True, l.get('by') or me_name
            to = l.get('to') or '전체'
            text = f"{'📢' if to == '전체' else '📨'} {to} · {l['text']}"
        cls = 's1-msg' + (' me' if me else '') + (' cast' if k == 'cast' else '')
        with ui.element('div').classes(cls).style(f'--c:{col}'):
            if not me:
                with ui.element('div').classes('av'):
                    if av:
                        ui.label(av)
                    else:
                        ui.icon('smart_toy')
            with ui.element('div').classes('bd'):
                ui.label(f'{who} · {S.hm(ts)}').classes('who')
                bb = ui.label(text).classes('bb')
                if inc:
                    bb.on('click', lambda e, i=inc['id']: select(i))

    def build_pins():
        nr = S.ops_metrics()['no_resp']
        if not nr:
            return
        with ui.element('div').classes('s1-pins'):
            for inc, role, ts in nr[:3]:
                site = S.state.sites[inc['site']]['name']
                pin = ui.element('div').classes('s1-pin')
                pin.on('click', lambda e, i=inc['id']: select(i))
                with pin:
                    ui.icon('phone_missed')
                    ui.label(f'{site} · {role} {staff_name(inc, role)} {S.ago(ts)} 미응답')

    def build_chat():
        with ui.element('div').classes('s1-feed'):            # 최신 메시지가 맨 아래
            for ts, k, l, inc in reversed(chat_entries()[-60:]):
                chat_msg(ts, k, l, inc)

    def build_badge():
        n = msg_count() - view['seen']
        if n > 0:
            ui.label(str(min(n, 99))).classes('s1-unread')

    def mark_seen():
        view['seen'] = msg_count()
        refs['badge'].refresh()

    # ── 채팅 받는 사람 선택 ──
    to_state = {'mode': 'all', 'hq': [], 'site': None, 'staff': [], 'q': ''}

    def site_staff(sid):
        """사업장 대응 인력 [(역할, 표시 이름, 사람 이름)]"""
        out = []
        for r in list(config.ESCALATION) + ['팀장']:
            p = S.staff_of(sid, r)
            if p:
                out.append((r, SITE_ROLE_NAME.get(r, r), p['name']))
        return out

    def to_label():
        """받는 사람 표시 문구 (선택이 없으면 None)"""
        m = to_state['mode']
        if m == 'all':
            return '전체'
        if m == 'hq':
            return ', '.join(r for r in HQ_ROLES if r in to_state['hq']) or None
        sid = to_state['site']
        if not sid or not to_state['staff']:
            return None
        names = [f'{n}({d})' for r, d, n in site_staff(sid) if r in to_state['staff']]
        return f"{S.state.sites[sid]['name']} " + ', '.join(names)

    def refresh_to():
        refs['to'].refresh()
        refs['hits'].refresh()

    def choose_site(sid):
        """사업장 선택: 그 사업장 대응 인력 전원을 기본 선택"""
        to_state['site'] = sid
        to_state['staff'] = [r for r, _, _ in site_staff(sid)] if sid else []
        to_state['q'] = ''
        site_q.set_value('')
        refresh_to()

    def set_mode(m):
        if m == 'inc':                                   # 현재 상황 → 그 사업장으로 사업장 지정
            inc = current()
            to_state['mode'] = 'site'
            site_q.set_visibility(True)
            choose_site(inc['site'] if inc else None)
            return
        to_state['mode'] = m
        site_q.set_visibility(m == 'site')
        refresh_to()

    def toggle(key, v):
        lst = to_state[key]
        lst.remove(v) if v in lst else lst.append(v)
        refresh_to()

    def send_cast():
        label = to_label()
        if not label:
            ui.notify('받는 사람을 선택하세요', type='warning')
            return
        if not (cast.value or '').strip():
            ui.notify('메시지를 입력하세요', type='warning')
            return
        try:
            S.broadcast(cast.value, S.state.operator or '관제사', to=label)
        except TypeError:
            ui.notify('state.py의 broadcast 함수를 최신 버전으로 바꿔 주세요', type='negative')
            return
        cast.set_value('')
        view['seen'] = msg_count()
        refs['chat'].refresh()
        refs['badge'].refresh()

    def build_to():
        with ui.element('div').classes('s1-to'):
            ui.label('받는 사람').classes('l')
            for key, label in [('all', '전체'), ('hq', '공단 상급 보고'), ('site', '사업장 지정')]:
                p = ui.label(label).classes('s1-tp' + (' on' if to_state['mode'] == key else ''))
                p.on('click', lambda e, k=key: set_mode(k))
            inc = current()
            if inc:
                p = ui.label(f"현재 상황 · {S.state.sites[inc['site']]['name']}").classes('s1-tp sub')
                p.on('click', lambda e: set_mode('inc'))

        if to_state['mode'] == 'hq':
            with ui.element('div').classes('s1-to'):
                for r in HQ_ROLES:
                    p = ui.label(r).classes('s1-tp sub' + (' on' if r in to_state['hq'] else ''))
                    p.on('click', lambda e, x=r: toggle('hq', x))

        sid = to_state['site']
        if to_state['mode'] == 'site' and sid:
            with ui.element('div').classes('s1-sitecard'):
                with ui.element('div').classes('nm'):
                    ui.label(S.state.sites[sid]['name'])
                    ui.label(S.state.sites[sid]['dept']).classes('s1-to-sum').style('margin-left:6px')
                    ui.space()
                    ui.icon('close').style('font-size:16px;cursor:pointer').on('click', lambda e: choose_site(None))
                with ui.element('div').classes('s1-to'):
                    for r, d, n in site_staff(sid):
                        p = ui.label(f'{d} {n}').classes('s1-tp sub' + (' on' if r in to_state['staff'] else ''))
                        p.on('click', lambda e, x=r: toggle('staff', x))

        label = to_label()
        ui.html(f'<div class="s1-to-sum">→ <b>{label}</b>에게 전파</div>' if label
                else '<div class="s1-to-sum">받는 사람을 선택하세요</div>')

    def build_hits():
        """사업장 지정: 검색어를 입력했을 때만 결과 목록 표시 (최대 6곳)"""
        q = to_state['q'].strip()
        if to_state['mode'] != 'site' or not q:
            return
        hits = [s for s in sorted(S.state.sites.values(), key=lambda x: x['name']) if q in s['name']][:6]
        with ui.element('div').classes('s1-hits'):
            if not hits:
                ui.label('검색 결과 없음').classes('s1-to-sum').style('padding:6px 10px')
            for s in hits:
                row = ui.element('div').classes('s1-hit')
                row.on('click', lambda e, x=s['id']: choose_site(x))
                with row:
                    ui.label(s['name'])
                    ui.html(f"<span>{s['dept']} · {s['gu']}</span>")

    # ── 상황 등록 창 (드롭다운 없이 창 안에서 선택) ──
    REG_DEFAULT = {'site': None, 'q': '', 'grade': config.GRADES[-1]['name'],
                   'cat': config.CATEGORIES[0], 'entry': '신고'}
    reg_state = dict(REG_DEFAULT)

    def pick(key, v):
        reg_state[key] = v
        if key == 'site':
            site_picker.refresh()
            site_label.refresh()
        else:
            reg_opts.refresh()

    def apply_type(name):
        info = S.state.types.get(name or '', {})
        if info.get('grade'):
            reg_state['grade'] = info['grade']
        if info.get('category') in config.CATEGORIES:
            reg_state['cat'] = info['category']
        if info.get('loc') and not f_loc.value:
            f_loc.set_value(info['loc'])
        reg_opts.refresh()

    def choose_type(name):
        f_type.set_value(name)
        apply_type(name)

    with ui.dialog() as reg, ui.card().classes('s1-reg'):
        with ui.row().classes('w-full items-center no-wrap'):
            ui.label('상황 등록').classes('s1-reg-t')
            ui.space()
            ui.button(icon='close', on_click=reg.close).props('flat round').style(f"color:{T['muted']}")

        with ui.element('div').classes('s1-reg-body'):
            # 왼쪽: 사업장 선택
            with ui.element('div').classes('s1-reg-col'):
                with ui.column().classes('w-full gap-0'):
                    @ui.refreshable
                    def site_label():
                        sid = reg_state['site']
                        with ui.element('div').classes('s1-reg-l'):
                            ui.label('사업장')
                            ui.label(S.state.sites[sid]['name'] if sid else '선택해 주세요').classes('sel')

                    site_label()
                    q_site = ui.input(placeholder='사업장 이름 검색').props('outlined clearable').classes('w-full')
                    q_site.on_value_change(lambda e: (reg_state.__setitem__('q', e.value or ''), site_picker.refresh()))

                    @ui.refreshable
                    def site_picker():
                        q = reg_state['q'].strip()
                        with ui.element('div').classes('s1-sitebox'):
                            for dept in config.DEPTS:
                                sites = [s for s in sorted(S.state.sites.values(), key=lambda x: x['name'])
                                         if s['dept'] == dept and (not q or q in s['name'])]
                                if not sites:
                                    continue
                                with ui.column().classes('w-full gap-0'):
                                    ui.label(dept).classes('s1-dept')
                                    with ui.element('div').classes('s1-sites'):
                                        for s in sites:
                                            chip = ui.element('div').classes(
                                                's1-site' + (' on' if reg_state['site'] == s['id'] else ''))
                                            chip.on('click', lambda e, x=s['id']: pick('site', x))
                                            with chip:
                                                ui.html(f"{s['name']}<span class='gu'>{s['gu']}</span>")

                    site_picker()

            # 오른쪽: 위치 · 유형 · 등급 · 분류 · 경로 · 설명
            with ui.element('div').classes('s1-reg-col'):
                with ui.column().classes('w-full gap-0'):
                    ui.label('발생 위치').classes('s1-reg-l')
                    f_loc = ui.input(placeholder='예: 2층 계단, 수영장 샤워실 입구').props('outlined').classes('w-full')
                with ui.column().classes('w-full gap-0'):
                    with ui.element('div').classes('s1-reg-l'):
                        ui.label('상황 유형')
                        ui.label('직접 입력하거나 아래에서 선택').classes('hint')
                    f_type = ui.input(placeholder='예: 응급환자, 화재').props('outlined').classes('w-full')

                    @ui.refreshable
                    def type_chips():
                        q = (f_type.value or '').strip()
                        names = [n for n in sorted(S.state.types) if not q or q in n][:12]
                        if not names:
                            return
                        with ui.element('div').classes('s1-tchips'):
                            for n in names:
                                t = ui.label(n).classes('s1-tchip' + (' on' if n == q else ''))
                                t.on('click', lambda e, x=n: choose_type(x))

                    type_chips()
                    f_type.on_value_change(lambda e: (type_chips.refresh(), apply_type(e.value)))

                @ui.refreshable
                def reg_opts():
                    groups = [('위험 등급', 'grade', [(g['name'], OPT_GRADE_COLOR.get(g['name'], B['blue']))
                                                    for g in config.GRADES]),
                              ('상황 분류', 'cat', [(c, B['blue']) for c in config.CATEGORIES]),
                              ('접수 경로', 'entry', [(e, '#4B5563') for e in config.ENTRY_ROUTES])]
                    for title, key, items in groups:
                        with ui.column().classes('w-full gap-0'):
                            ui.label(title).classes('s1-reg-l')
                            with ui.element('div').classes('s1-opts'):
                                for v, col in items:
                                    o = ui.label(v).classes('s1-opt' + (' on' if reg_state[key] == v else '')) \
                                        .style(f'--c:{col}')
                                    o.on('click', lambda e, k=key, x=v: pick(k, x))

                reg_opts()
                with ui.column().classes('w-full gap-0'):
                    ui.label('상황 설명 (선택)').classes('s1-reg-l')
                    f_desc = ui.textarea(placeholder='신고 내용, 현장 상태 등').props('outlined autogrow').classes('w-full')

        def submit():
            if not (reg_state['site'] and (f_loc.value or '').strip() and (f_type.value or '').strip()):
                ui.notify('사업장 · 발생 위치 · 상황 유형을 입력하세요', type='warning')
                return
            inc = S.create_incident(reg_state['site'], f_loc.value.strip(), f_type.value.strip(), reg_state['grade'],
                                    reg_state['entry'], (f_desc.value or '').strip(), category=reg_state['cat'])
            reg.close()
            ui.notify(f"{S.state.sites[inc['site']]['name']} · {inc['type']} 접수", type='positive')
            select(inc['id'])

        with ui.row().classes('w-full justify-end gap-3'):
            ui.button('취소', on_click=reg.close).props('flat no-caps').style('font-size:20px')
            ui.button('접수', on_click=submit).props('unelevated no-caps') \
                .style(f"background:{B['blue']} !important;color:#fff !important;font-size:20px;padding:8px 44px")

    def open_reg():
        """등록 창을 열 때마다 입력값 초기화"""
        reg_state.update(REG_DEFAULT)
        for el in (q_site, f_loc, f_type, f_desc):
            el.set_value('')
        site_label.refresh()
        site_picker.refresh()
        type_chips.refresh()
        reg_opts.refresh()
        reg.open()

    # ── 종결 기록: 처리된 보고서 다시 보기 ──
    hist = {'sel': None, 'q': '', 'day': '전체'}
    DAY_TABS = ['전체', '금일', '전일']

    def day_of(inc):
        return '전일' if inc['id'] < 0 else '금일'

    def closed_list():
        """종결 기록 = 금일 종결 + 전일 기록. 검색은 칩 범위 안에서 사업장 · 유형 · 담당자"""
        q = hist['q'].strip()
        rows = [i for i in S.state.incidents if S.is_closed(i)] + list(S.state.history)
        if hist['day'] != '전체':
            rows = [i for i in rows if day_of(i) == hist['day']]
        if q:
            rows = [i for i in rows if q in S.state.sites[i['site']]['name'] or q in i['type'] or q in i['handler']]
        return sorted(rows, key=lambda i: i.get('closed') or i['start'], reverse=True)

    def open_hist():
        rows = closed_list()
        if rows and not any(i['id'] == hist['sel'] for i in rows):
            hist['sel'] = rows[0]['id']
        hist_ov.set_visibility(True)
        refs['hlist'].refresh()
        refs['hbody'].refresh()

    def close_hist():
        hist_ov.set_visibility(False)

    def pick_hist(iid):
        hist['sel'] = iid
        refs['hlist'].refresh()
        refs['hbody'].refresh()

    def set_day(d):
        hist['day'] = d
        refs['hlist'].refresh()

    def build_hcount():
        n = sum(1 for i in S.state.incidents if S.is_closed(i)) + len(S.state.history)
        ui.label(f"{n}건").classes('n')

    def build_hlist():
        rows = closed_list()
        with ui.row().classes('items-center gap-2 no-wrap').style('margin:4px 0 6px'):
            for d in DAY_TABS:
                n = len([i for i in S.state.incidents if S.is_closed(i)]) if d == '금일' else \
                    len(S.state.history) if d == '전일' else \
                    sum(1 for i in S.state.incidents if S.is_closed(i)) + len(S.state.history)
                chip = ui.element('div').classes('s1-kp' + (' on' if hist['day'] == d else '')).style('font-size:17px;padding:6px 14px')
                chip.on('click', lambda e, x=d: set_day(x))
                with chip:
                    ui.label(d)
                    ui.html(f'<b style="font-size:17px">{n}</b>')
        with ui.element('div').classes('s1-hitems'):
            if not rows:
                ui.label('종결된 상황 없음').classes('s1-hempty').style('height:auto;padding:40px')
            last = None
            for inc in rows:
                d = day_of(inc)
                if d != last:
                    last = d
                    cnt = sum(1 for i in rows if day_of(i) == d)
                    ui.label(f'{d} · {cnt}건').style('font-size:16px;font-weight:700;color:#4B5563;padding:12px 6px 4px')
                site = S.state.sites[inc['site']]
                item = ui.element('div').classes('s1-hi' + (' on' if hist['sel'] == inc['id'] else ''))
                item.on('click', lambda e, i=inc['id']: pick_hist(i))
                with item:
                    with ui.element('div').classes('top'):
                        ui.html(grade_html(inc['grade']))
                        ui.label(inc['type']).classes('ty')
                        if inc.get('false_alarm'):
                            ui.label('오경보').classes('s1-fa')
                        ui.label(S.md_hm(inc.get('closed') or inc['start'])).classes('tm')
                    ui.label(f"{site['name']} · {inc['loc']} · 담당 {inc['handler'] or '-'}").classes('sub')

    def build_hbody():
        inc = S.get_incident(hist['sel']) if hist['sel'] else None
        if not inc or not S.is_closed(inc):
            ui.label('왼쪽에서 종결 기록을 선택하세요').classes('s1-hempty')
            return
        site = S.state.sites[inc['site']]
        fc = S.first_call_ts(inc)
        act = S.stage_times(inc).get(config.ACTION_DONE_STAGE)
        end = inc.get('closed')
        with ui.row().classes('w-full items-center no-wrap gap-3'):
            grade(inc['grade'])
            ui.label(inc['type']).classes('s1-dtitle')
            if inc.get('false_alarm'):
                ui.label('오경보 종결').classes('s1-fa').style('font-size:18px')
        ui.label(f"{site['name']} ({site['dept']}) · {inc['loc']} · 접수 {S.md_hm(inc['start'])}"
                 + (f" · 종결 {S.md_hm(end)}" if end else '')).classes('s1-dsub').style('font-size:20px')
        with ui.element('div').classes('s1-hstats'):
            for label, start, stop in [('초동 시간 · 접수 → 첫 호출·신고', inc['start'], fc),
                                       ('조치 시간 · 접수 → 조치 완료', inc['start'], act),
                                       ('총 처리 시간 · 접수 → 종결', inc['start'], end)]:
                with ui.element('div').classes('s1-hstat'):
                    ui.label(label).classes('l')
                    ui.label(fmt_min((stop - start) / 60) if stop else '-').classes('v')
        with ui.element('div').classes('s1-sec'):
            sec_title('description', '보고서')
            rep = inc['report']
            rows = [('담당자', inc['handler']), ('세부 위치', rep['loc_detail']), ('피해 내용', rep['damage']),
                    ('조치 결과', rep['result']), ('원인', rep['cause']),
                    ('상황 분류', inc['category']),
                    ('접수 경로', inc['entry']), ('상황 설명', inc['desc'])]
            with ui.element('div').classes('s1-repv'):
                for k, v in rows:
                    ui.label(k).classes('k')
                    ui.label(v or '-')
        with ui.element('div').classes('s1-sec'):
            items = S.checklist_for(inc)
            sec_title('task_alt', '체크리스트', f"완료 {len(inc['checks'])} / {len(items)}")
            for idx, it in enumerate(items):
                on = idx in inc['checks']
                with ui.element('div').classes('s1-hcheck'):
                    ui.icon('check_circle' if on else 'radio_button_unchecked') \
                        .style(f"color:{C['ok'] if on else '#C5CCD5'}")
                    ui.label(it['text']).style('' if on else 'color:#6B7280')
                    ui.label(S.hm(inc['checks'][idx]) if on else '미완료').classes('t')
        with ui.element('div').classes('s1-sec'):
            sec_title('history_edu', '처리 경과', f"{len(inc['log'])}건")
            with ui.element('div').classes('s1-tl'):
                for l in sorted(inc['log'], key=lambda x: x['ts']):
                    m = l['kind'] == 'memo'
                    with ui.element('div').classes('s1-tl-item' + (' memo' if m else '')):
                        ui.label(l['text']).classes('s1-tl-text')
                        who = f" · {l['author']}" if m and l.get('author') else ''
                        ui.label(f"{S.md_hm(l['ts'])}{' · 조치 메모' if m else ''}{who}").classes('s1-tl-time')

    # ── 처리 이력 내보내기 (현재 기록으로 CSV 생성) ──
    def export_csv():
        """처리 이력 내보내기: 전일 기록 + 금일 상황"""
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['번호', '일자', '사업장', '사업단', '발생위치', '상황유형', '분류', '위험등급', '접수경로', '접수시각',
                    '처리단계', '첫 호출·신고', '초동(분)', '조치 완료', '조치(분)', '종결', '담당자', '반복', '조치 메모'])
        for k, inc in enumerate(sorted(S.state.history + S.state.incidents, key=lambda i: i['start']), 1):
            site = S.state.sites[inc['site']]
            fc = S.first_call_ts(inc)
            act = S.stage_times(inc).get(config.ACTION_DONE_STAGE)
            memos = ' / '.join(l['text'] for l in inc['log'] if l['kind'] == 'memo')
            w.writerow([k, day_of(inc), site['name'], site['dept'], inc['loc'], inc['type'], inc['category'], inc['grade'],
                        inc['entry'], S.md_hm(inc['start']), inc['stage'],
                        S.md_hm(fc) if fc else '', f"{(fc - inc['start']) / 60:.1f}" if fc else '',
                        S.md_hm(act) if act else '', f"{(act - inc['start']) / 60:.1f}" if act else '',
                        S.md_hm(inc['closed']) if inc.get('closed') else '', inc['handler'], inc['repeat'], memos])
        ui.download.content(buf.getvalue().encode('utf-8-sig'), f"상황처리이력_{time.strftime('%Y%m%d_%H%M')}.csv")

    # ── 슬라이드 상세 ──
    def track(inc):
        cur = S.STAGE_INDEX[inc['stage']]
        parts = ''.join(f'<div class="st{" done" if i < cur else " now" if i == cur else ""}"><i></i>{st}</div>'
                        for i, st in enumerate(config.STAGES))
        ui.html(f'<div class="s1-track" style="--c:{stage_color(inc)}">{parts}</div>').classes('w-full')

    def stage_sec(inc):
        with ui.element('div').classes('s1-sec'):
            sec_title('route', '처리 단계', NEXT_ACTION[inc['stage']])
            track(inc)
            if S.is_open(inc):
                with ui.row().classes('w-full justify-end').style('margin-top:18px'):
                    nxt = config.STAGES[S.STAGE_INDEX[inc['stage']] + 1]
                    ui.button(f'다음 단계: {nxt}', icon='arrow_forward', on_click=lambda: S.advance(inc['id'])) \
                        .props('unelevated no-caps') \
                        .style(f"background:{B['blue']} !important;color:#fff !important;font-size:19px")

    def call_card(inc, target):
        status, ts = S.call_status(inc, target)
        called = status != '미호출'
        ext = target in S.EXTERNAL
        need = ext and not called and S.is_high(inc) and S.needs_external(inc, target)
        absent = not ext and not called and S.is_absent(inc, target)
        site = S.state.sites[inc['site']]['name']
        title = f'{target} 신고' if ext else f'{target} 호출'
        if ext:
            sub = f'{S.hm(ts)} 신고함 · 자동 신고 연동' if called else '누르면 자동 신고'
        elif absent:
            sub = f'{S.absence(inc, target)} 부재 → 차순위 바로 호출'
        elif status == '미호출':
            sub = f'{site} · 누르면 호출'
        elif status == '호출 중':
            sub = f'{S.hm(ts)} 호출 · 응답 대기 {S.ago(ts)}'
        elif status == '미응답':
            sub = f'{S.ago(ts)} 미응답 → 차순위 호출'
        else:
            sub = f'{S.hm(ts)} 응답 완료'
        card = ui.element('div').classes('s1-call' + ('' if called else ' click') + (' need' if need else ''))
        if not called:
            card.on('click', lambda e: S.notify(inc['id'], target))
        icon = 'local_police' if target == '112' else 'call'
        ic_color = C['alarm'] if (target == '119' or need) else B['blue']
        sub_color = C['alarm'] if need else C['warn'] if absent else CALL_COLOR.get(status, T['muted'])
        with card:
            with ui.element('div').classes('ic'):
                ui.icon(icon).style(f'color:{ic_color}')
            with ui.column().classes('gap-0').style('min-width:0'):
                ui.label(title).classes('s1-call-title')
                ui.label(sub).classes('s1-call-sub').style(
                    f'color:{sub_color};' + ('font-weight:600' if called or absent or need else ''))
            ui.space()
            if status in ('호출 중', '미응답'):
                ui.button('응답 확인', on_click=lambda: S.respond_call(inc['id'], target)) \
                    .props('outline dense no-caps').style('font-size:16px;flex-shrink:0;padding:2px 12px')

    def escalation_row(inc):
        order = S.order_of(inc)
        first_ok = S.call_status(inc, order[0])[0] == '응답'
        escalated = any(S.call_status(inc, r)[0] != '미호출' for r in order[1:])
        with ui.element('div').classes('s1-line'):
            ui.label('현장 차순위').classes('k')
            if first_ok and not escalated:
                ui.label(f'{order[0]} 응답 · 차순위 호출 불필요').style(f"color:{C['ok']};font-weight:600")
                return
            ui.label(f'{S.no_response_min(inc)}분 미응답·부재 시').classes('sg-muted').style('font-size:17px')
            ui.space()
            for role in order[1:]:
                status, ts = S.call_status(inc, role)
                if status == '미호출':
                    ok = S.can_call(inc, role)
                    label = f'{role} 호출' + (f' ({S.absence(inc, role)})' if S.is_absent(inc, role) else '')
                    btn = ui.button(label, on_click=lambda e, r=role: S.notify(inc['id'], r)) \
                        .props('unelevated dense no-caps') \
                        .style(f"background:{B['blue'] if ok else T['line']} !important;"
                               f"color:{'#fff' if ok else T['muted']} !important")
                    if not ok:
                        btn.disable()
                else:
                    tag(f'{role} · {status} {S.hm(ts)}', CALL_COLOR[status])
                    if status in ('호출 중', '미응답'):
                        ui.button('응답', on_click=lambda e, r=role: S.respond_call(inc['id'], r)) \
                            .props('outline dense no-caps')

    def report_row(inc):
        """내부 보고: 재난안전상황실·팀장 동시 보고, 중대 상황만 경영진 (응답 대기 없음)"""
        timing = S.report_timing(inc)
        with ui.element('div').classes('s1-line'):
            ui.label('내부 보고').classes('k')
            ui.label('재난안전상황실·팀장 동시' + (' · 경영진' if S.needs_senior(inc) else '')) \
                .classes('sg-muted').style('font-size:17px')
            ui.space()
            for role in S.report_targets(inc):
                status, ts = S.call_status(inc, role)
                name = f'{role} 보고'
                if status == '미호출':
                    color = C['alarm'] if '즉시' in timing[role] else B['blue']
                    ui.button(f'{name} · {timing[role]}', on_click=lambda e, r=role: S.notify(inc['id'], r)) \
                        .props('unelevated dense no-caps') \
                        .style(f"background:{color} !important;color:#fff !important")
                else:
                    tag(f'{name} 완료 · {S.hm(ts)}', CALL_COLOR[status])

    def checklist(inc):
        """체크리스트: 종류는 색 알약, 근거는 ⓘ에 마우스를 올릴 때만 표시"""
        post_shown = False
        with ui.element('div').classes('s1-checks'):
            for idx, it in enumerate(S.checklist_for(inc)):
                on = idx in inc['checks']
                post = it['text'].startswith('[사후]')
                if post and not post_shown:
                    ui.label('종결 후 진행 · 종결 조건 아님').classes('s1-post-head')
                    post_shown = True
                toggle = lambda e=None, k=idx, t=it['text']: S.toggle_check(inc['id'], k, t)
                with ui.element('div').classes('s1-check' + (' done' if on else '') + (' post' if post else '')):
                    if on:
                        ui.icon('check_circle').style(f"font-size:38px;color:{C['ok']};cursor:pointer").on('click', toggle)
                    else:
                        ui.label(str(idx + 1)).classes('s1-no')
                    ui.label(it['kind']).classes('s1-kind').style(f"--c:{KIND_COLOR.get(it['kind'], '#6B7280')}")
                    ui.label(it['text'].replace('[사후] ', '')).classes('s1-check-text').style('flex:1;min-width:0')
                    if it.get('basis'):
                        basis = str(it['basis']).replace('"', "'")
                        ui.icon('info').classes('s1-basis').props(f'title="근거: {basis}"')
                    if on:
                        ui.label(S.hm(inc['checks'][idx])).classes('s1-check-time')
                    else:
                        ui.button('완료', on_click=toggle).props('outline dense no-caps')

    def box_todo(inc):
        items = S.checklist_for(inc)
        main = [i for i, it in enumerate(items) if not it['text'].startswith('[사후]')]
        done = sum(1 for i in main if i in inc['checks'])
        from_excel = bool(S.state.checklists.get(inc['type']))
        with ui.element('div').classes('s1-sec'):
            sec_title('task_alt', '지금 할 일',
                      f'체크리스트 {done} / {len(main)}' + ('' if from_excel else ' · 공통 체크리스트'))
            with ui.element('div').classes('s1-calls'):
                call_card(inc, '119')
                call_card(inc, '112')
                call_card(inc, S.order_of(inc)[0])
            escalation_row(inc)
            report_row(inc)
            checklist(inc)

    def box_report(inc):
        """보고서 작성·종결 (조치 완료 단계). 비어 있는 항목은 기본값으로 미리 채움"""
        if not inc['report']['loc_detail']:
            S.set_report(inc['id'], 'loc_detail', inc['loc'])              # 세부 위치 = 발생 위치
        if not inc['handler']:
            for r in S.order_of(inc):                                        # 담당자 = 응답한 현장 인력
                if S.call_status(inc, r)[0] == '응답':
                    p = S.staff_of(inc['site'], r)
                    if p:
                        S.set_handler(inc['id'], p['name'])
                        break

        placeholders = {'handler': '현장 대응 담당자 이름', 'loc_detail': '예: 2층 계단 하단',
                        'damage': '인명·시설 피해 내용 (없으면 "없음")', 'result': '현장에서 한 조치와 현재 상태',
                        'cause': '추정 원인 (선택)'}

        def do_close():
            if S.close_incident(inc['id']):
                ui.notify('보고 완료 · 종결 처리했습니다', type='positive')
                clear()

        @ui.refreshable
        def close_area():
            miss = S.close_missing(inc)
            with ui.element('div').classes('s1-rfoot'):
                if miss:
                    ui.label('남은 항목').classes('s1-rmiss-l')
                    for m in miss:
                        text = '조치 메모 1건 (오른쪽 상황일지에 입력)' if m.startswith('조치 메모') else m
                        ui.html(f'<span class="s1-tag" style="--c:{C["alarm"]}">{text}</span>')
                else:
                    ui.html(f'<span class="s1-tag" style="--c:{C["ok"]}">✓ 모든 항목 입력 완료</span>')
                ui.space()
                btn = ui.button('보고 완료 · 종결', icon='task_alt', on_click=do_close).props('unelevated no-caps') \
                    .style(f"background:{T['line'] if miss else C['ok']} !important;"
                           f"color:{T['muted'] if miss else '#fff'} !important;font-size:20px;padding:8px 28px")
                if miss:
                    btn.disable()

        def on_change(key, value):
            if key == 'handler':
                S.set_handler(inc['id'], value)
            else:
                S.set_report(inc['id'], key, value)
            close_area.refresh()

        with ui.element('div').classes('s1-sec'):
            with ui.element('div').classes('s1-report'):
                with ui.element('div').classes('s1-report-hd'):
                    ui.icon('edit_note')
                    with ui.column().classes('gap-0'):
                        ui.label('보고서 작성').classes('t')
                        ui.label('조치가 완료되었습니다. 아래 항목을 입력하고 종결하세요.').classes('s')
                with ui.element('div').classes('s1-rgrid'):
                    for key, label, multi in REPORT_FIELDS:
                        val = inc['handler'] if key == 'handler' else inc['report'][key]
                        with ui.column().classes('w-full gap-0').style('grid-column:1 / -1' if multi else ''):
                            ui.label(label).classes('s1-rl')
                            el = (ui.textarea if multi else ui.input)(value=val, placeholder=placeholders[key]) \
                                .props('outlined autogrow' if multi else 'outlined').classes('w-full')
                            el.on_value_change(lambda e, k=key: on_change(k, e.value))
                close_area()

    def box_info(inc):
        site = S.state.sites[inc['site']]
        cat = inc['category']
        rows = [('사업장', f"{site['name']} ({site['dept']})"), ('주소', config.full_addr(site)),
                ('발생 위치', inc['loc']), ('상황 유형', f"{inc['type']} · {cat}"), ('접수 경로', inc['entry']),
                ('발생 시각', f"{S.md_hm(inc['start'])} · {S.ago(inc['start'])} 경과"),
                ('반복', f"총 {inc['repeat']}회 발생"), ('상황 설명', inc['desc'] or '-')]
        with ui.element('div').classes('s1-sec'):
            sec_title('assignment', '접수 내역')
            with ui.element('div').classes('s1-info'):
                for k, v in rows:
                    ui.label(k).classes('k')
                    ui.label(v)

    def box_log(inc):
        with ui.element('div').classes('s1-sec'):
            sec_title('history_edu', '상황일지', f"{len(inc['log'])}건")
            with ui.element('div').classes('s1-memo') \
                    .style('display:flex;flex-direction:row;flex-wrap:nowrap;align-items:center;gap:12px;width:100%'):
                memo = ui.input(placeholder='조치 내용 입력 후 Enter', value=view['memo']) \
                    .props('outlined hide-bottom-space').classes('s1-memo-in').style('flex:1;min-width:0')
                memo.on_value_change(lambda e: view.__setitem__('memo', e.value))

                def save():
                    if S.add_memo(inc['id'], view['memo'], S.state.operator or '관제사'):
                        view['memo'] = ''

                memo.on('keydown.enter', save)
                ui.button('기록', icon='edit_note', on_click=save).props('unelevated no-caps').classes('s1-memo-btn')
            with ui.element('div').classes('s1-tl'):
                for l in sorted(inc['log'], key=lambda x: x['ts'], reverse=True):
                    m = l['kind'] == 'memo'
                    with ui.element('div').classes('s1-tl-item' + (' memo' if m else '')):
                        ui.label(l['text']).classes('s1-tl-text')
                        who = f" · {l['author']}" if m and l.get('author') else ''
                        ui.label(f"{S.hm(l['ts'])}{' · 조치 메모' if m else ''}{who}").classes('s1-tl-time')

    def card_a(inc):
        site = S.state.sites[inc['site']]
        high = S.is_high(inc) and S.is_open(inc)
        with ui.element('div').classes('s1-card a' + (' high' if high else '')):
            with ui.element('div').classes('s1-card-head'):
                with ui.column().classes('gap-0').style('flex:1;min-width:0'):
                    with ui.row().classes('items-center gap-3 no-wrap'):
                        grade(inc['grade'])
                        ui.label(inc['type']).classes('s1-dtitle')
                    ui.label(f"{site['name']} · {inc['loc']} · {S.md_hm(inc['start'])} 접수 · "
                             f"{S.ago(inc['start'])} 경과").classes('s1-dsub')
                urgent = urgent_list()
                if S.card_of(inc) == URGENT and len(urgent) > 1:
                    ids = [u['id'] for u in urgent]
                    nxt_id = ids[(ids.index(inc['id']) + 1) % len(ids)]
                    ui.button(f'다음 긴급 건 ({len(urgent)})', icon='arrow_forward', on_click=lambda: select(nxt_id)) \
                        .props('outline dense no-caps').style(f"color:{C['alarm']} !important;font-size:16px")
                ui.button(icon='close', on_click=clear).props('flat round dense') \
                    .style(f"color:{T['muted']};font-size:18px").tooltip('닫기 (Esc)')
            with ui.element('div').classes('s1-card-body'):
                stage_sec(inc)
                if S.needs_report(inc):
                    box_report(inc)
                box_todo(inc)

    def card_b(inc):
        with ui.element('div').classes('s1-card b'):
            with ui.element('div').classes('s1-card-head').style('align-items:center'):
                ui.icon('assignment').classes('sg-ico').style('font-size:28px')
                ui.label('접수 내역 · 상황일지').classes('t')
            with ui.element('div').classes('s1-card-body'):
                box_info(inc)
                box_log(inc)

    def build_overlay():
        inc = current()
        if not inc:
            return
        anim, view['anim'] = view['anim'], False
        with ui.element('div').classes('s1-ov'):
            ui.element('div').classes('s1-dim').on('click', lambda e: clear())
            with ui.element('div').classes('s1-drawer' + (' anim' if anim else '')):
                card_a(inc)
                card_b(inc)

    # ── 갱신 · 경고음 · 단축키 ──
    def periodic():
        inc = current()
        if not inc or view['memo'] or S.needs_report(inc):
            return
        refs['ov'].refresh()

    seen = {i['id'] for i in S.state.incidents}

    def check_alarm():
        new = [i for i in S.state.incidents if i['id'] not in seen]
        seen.update(i['id'] for i in new)
        high = [i for i in new if S.is_high(i)]
        if high:
            view['detail'], view['memo'], view['anim'] = high[-1]['id'], '', True
            ui.run_javascript(BEEP_JS)
            refs['ov'].refresh()

    def on_key(e):
        if not (e.key.name == 'Escape' and e.action.keydown):
            return
        if hist_ov.visible:
            close_hist()
        elif current():
            clear()

    # ── 화면 배치 ──
    view['seen'] = msg_count()                     # 처음 열 때는 안 읽은 메시지 0
    with screen_root():
        with header('긴급 · 미조치 알림'):
            live(build_head, every=30)
            clock()
        with ui.element('div').classes('sg-body'):
            refs['main'] = live(build_main, every=20)
        refs['ov'] = live(build_overlay)

    # 종결 기록 (상황목록 머리줄 [종결 기록]으로 열기)
    hist_ov = ui.element('div').classes('s1-ov s1-hov')
    hist_ov.set_visibility(False)
    with hist_ov:
        ui.element('div').classes('s1-dim').on('click', lambda e: close_hist())
        with ui.element('div').classes('s1-hist'):
            with ui.element('div').classes('s1-hlist'):
                with ui.element('div').classes('s1-hhd'):
                    with ui.element('div').classes('s1-ht'):
                        ui.icon('history')
                        ui.label('종결 기록')
                        live(build_hcount)
                        ui.space()
                        ui.button(icon='close', on_click=close_hist).props('flat round dense') \
                            .style(f"color:{T['muted']};background:#EEF1F4")
                    with ui.input(placeholder='사업장 · 상황 유형 · 담당자 검색').props('outlined clearable') \
                            .classes('w-full s1-hsearch') as hq:
                        with hq.add_slot('prepend'):
                            ui.icon('search')
                    hq.on_value_change(lambda e: (hist.__setitem__('q', e.value or ''), refs['hlist'].refresh()))
                refs['hlist'] = live(build_hlist)
            with ui.element('div').classes('s1-hbody'):
                refs['hbody'] = live(build_hbody)

    # 내부 채팅방: 오른쪽 끝에 마우스를 대면 열림
    ui.element('div').classes('s1-chat-zone')
    with ui.element('div').classes('s1-chat-handle'):
        ui.icon('forum')
        ui.label('내부 채팅')
        refs['badge'] = live(build_badge)
    chat = ui.element('div').classes('s1-chat')
    chat.on('mouseenter', lambda e: mark_seen())
    with chat:
        with ui.element('div').classes('s1-chat-head'):
            with ui.element('div').classes('s1-chat-t'):
                ui.icon('forum')
                ui.label('SG 상황 공유방')
            ui.label('관제사 · 사업장 담당자 · 당직자 · 팀장 · 재난안전실 · 경영진').classes('s1-chat-s')
            with ui.element('div').classes('s1-members'):
                for name, col in MEMBERS:
                    ui.label(name[:1]).classes('s1-mem').style(f'--c:{col}').props(f'title="{name}"')
                ui.html(f'<span>참여 {len(S.state.staff) + 1}명</span>')
        live(build_pins)
        refs['chat'] = live(build_chat, every=30)
        with ui.element('div').classes('s1-compose'):
            refs['to'] = live(build_to)
            site_q = ui.input(placeholder='사업장 이름 검색').props('outlined dense clearable').classes('w-full') \
                .style('font-size:14px')
            site_q.on_value_change(lambda e: (to_state.__setitem__('q', e.value or ''), refs['hits'].refresh()))
            site_q.set_visibility(False)
            refs['hits'] = live(build_hits)
            with ui.element('div').classes('s1-send-row'):
                cast = ui.input(placeholder='메시지 입력 후 Enter').props('outlined dense').classes('w-full') \
                    .style('font-size:14px')
                cast.on('keydown.enter', send_cast)
                ui.button(icon='send', on_click=send_cast).props('unelevated round dense') \
                    .style(f"background:{B['blue']} !important;color:#fff !important")

    ui.keyboard(on_key=on_key)
    ui.timer(20, periodic)
    ui.timer(0.5, check_alarm)