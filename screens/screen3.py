"""화면3 · 사업장별 현황 (v6)
제목 옆 페이지 전환: [상황 보드] 미조치 → 확인 필요 → 이상 → 확인 불가 / [전체 사업장] 분석형 배치
위: 운영 지표 줄 · 지역 / 사업단 / AI·경보 연계 필터 + 검색 (두 페이지 공통)
상세: 사진 · 경고 띠 · 정기 보고/설비 · 주변 사업장 · 미조치/이상 입력 | 보고 기록 · 중요설비
위치는 화면2 지도가 담당 (상세를 열면 화면2 지도도 그 사업장으로 이동)
화면1에서 상황을 고르면 해당 사업장 상세가 자동으로 열림."""
import math

from nicegui import ui

import config
import geo
import state as S
from screens import screen_root, header, live, clock, grade_html, step_html, T, C, B
from screens.screen4 import short_tag        # 상황 꼬리표 (화면4와 같은 기준)

GRAY = C['unknown']
ORDER = ['미조치', '확인 불가', '확인 필요', '이상', '정상']
COLS = [('미조치', '처리 진행 중'), ('확인 필요', '정기 보고 미수신'),
        ('이상', '이상 보고 · 설비 경보'), ('확인 불가', '시스템 연결 끊김')]
LEGEND = ['미조치', '확인 필요', '이상', '확인 불가', '정상']
STATUS_TEXT = {'확인 필요': '#8A5A00', '이상': '#A85400', '미조치': '#C62828', '확인 불가': '#374151', '정상': '#1E7A34'}
KEY_TEXT = {'재난': '#7A0916', '긴급': '#C62828', '주의': '#A85400', '알림': '#7A5F00'}
EQUIP_COLOR = {'정상': C['ok'], '주의': C['warn'], '경보': C['alarm']}
EQUIP_TEXT = {'주의': '#A85400', '경보': '#C62828'}
REPORT_COLOR = {'정상': C['ok'], '이상': C['warn'], '주의': C['warn']}
DEPT_COLOR = {'청소년사업단': '#7C5CC4', '도서관사업단': '#2783C5', '체육1사업단': '#1495BD', '체육2사업단': '#0E8F80',
              '청사관리부': '#55657A', '공원관리부': '#6E8A0A', '주차사업부': '#C77700', '재활사업부': '#B4456E',
              '복지사업단': '#D0583E'}
DEPT_SHORT = {'청소년사업단': '청소년', '도서관사업단': '도서관', '체육1사업단': '체육1', '체육2사업단': '체육2',
              '청사관리부': '청사', '공원관리부': '공원', '주차사업부': '주차', '재활사업부': '재활', '복지사업단': '복지'}
BAR_COLOR = {'ok': B['sky'], 'soon': '#F2B33D', 'over': '#E08A00'}
BAR_TEXT = {'ok': T['muted'], 'soon': '#9A6A00', 'over': '#8A5A00'}
REQUEST_TEXT = '정기 보고가 들어오지 않았습니다. 현장 상황 확인 후 보고 바랍니다.'

CSS = f"""
<style>
/* ===== 제목 옆 페이지 전환 ===== */
.s3-ptabs {{ display:inline-flex; gap:4px; padding:5px; margin-left:12px; border-radius:999px; background:#ECEFF3; }}
.s3-ptab {{ display:flex; align-items:center; gap:8px; padding:8px 22px; border-radius:999px; font-size:21px; font-weight:650;
           color:{T['muted']}; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s3-ptab .q-icon {{ font-size:24px; }}
.s3-ptab b {{ font-size:17px; font-variant-numeric:tabular-nums; }}
.s3-ptab.on {{ background:{T['panel']}; color:{B['blue']}; box-shadow:0 2px 8px rgba(16,24,40,.08); }}

/* ===== 운영 지표 줄 ===== */
.s3-kpi {{ display:grid; grid-template-columns:repeat(5, 1fr); padding:22px 8px; flex-shrink:0; }}
.s3-k {{ display:flex; align-items:center; gap:18px; padding:4px 26px; min-width:0; }}
.s3-k + .s3-k {{ border-left:1px solid #EEF0F3; }}
.s3-k .ic {{ width:64px; height:64px; border-radius:18px; flex-shrink:0; display:flex; align-items:center; justify-content:center;
            color:var(--i); background:color-mix(in srgb, var(--i) 14%, #fff); }}
.s3-k .ic .q-icon {{ font-size:34px; }}
.s3-k .l {{ font-size:20px; font-weight:600; color:#4B5563; }}
.s3-k .v {{ font-size:38px; font-weight:800; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; line-height:1.15; }}
.s3-k .b {{ margin-left:auto; padding:6px 16px; border-radius:999px; font-size:18px; font-weight:700; white-space:nowrap;
           color:var(--t); background:color-mix(in srgb, var(--c) 16%, #fff); }}

/* ===== 필터 ===== */
.s3-frow {{ display:flex; align-items:center; gap:12px; flex-shrink:0; }}
.s3-seg {{ display:inline-flex; gap:4px; padding:5px; border-radius:999px; background:#E4E8EC; }}
.s3-seg > div {{ display:flex; align-items:center; gap:8px; padding:10px 24px; border-radius:999px; font-size:20px;
                font-weight:650; color:#4B5563; cursor:pointer; transition:all .2s var(--sg-ease); }}
.s3-seg > div b {{ font-size:17px; color:#6B7280; font-variant-numeric:tabular-nums; }}
.s3-seg > div.on {{ background:#fff; color:{T['text']}; box-shadow:0 2px 8px rgba(16,24,40,.10); }}
.s3-fc {{ display:inline-flex; align-items:center; gap:8px; padding:11px 20px; border-radius:999px; background:#fff;
         box-shadow:inset 0 0 0 1.5px #D3D9E0; font-size:20px; font-weight:650; color:#374151; cursor:pointer;
         white-space:nowrap; transition:all .2s var(--sg-ease); }}
.s3-fc .q-icon {{ font-size:24px; }}
.s3-fc:hover {{ box-shadow:inset 0 0 0 1.5px {B['blue']}; }}
.s3-fc.on {{ background:{B['blue']}; color:#fff; box-shadow:none; }}
.s3-depts {{ display:flex; flex-wrap:wrap; gap:8px; flex-shrink:0; padding:14px 16px; border-radius:18px; background:#fff;
            box-shadow:var(--sg-shadow); }}
.s3-count {{ font-size:19px; color:#4B5563; white-space:nowrap; }}
.s3-search {{ width:620px; }}
.s3-search .q-field__control {{ background:#fff !important; border-radius:16px !important; min-height:64px;
                               box-shadow:inset 0 0 0 1.5px #C9D1DA; }}
.s3-search.q-field--focused .q-field__control {{ box-shadow:inset 0 0 0 2px {B['blue']}; }}
.s3-search .q-field__native {{ font-size:22px !important; }}
.s3-search .q-field__prepend .q-icon {{ font-size:28px; color:#6B7280; }}
.s3-dtag {{ display:inline-flex; align-items:center; padding:5px 12px; border-radius:8px; font-size:18px; font-weight:700;
           white-space:nowrap; flex-shrink:0; color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fff); }}

/* ===== 상황 보드 ===== */
.s3-board {{ flex:1; min-height:0; display:grid; grid-template-columns:repeat(4, 1fr); gap:18px; }}
.s3-col {{ min-height:0; display:flex; flex-direction:column; padding:18px 14px 14px; border-radius:22px; background:#EDF0F3; }}
.s3-colh {{ display:flex; align-items:center; gap:12px; padding:2px 8px 16px; font-size:26px; font-weight:800; flex-shrink:0; }}
.s3-colh .dot {{ width:16px; height:16px; border-radius:50%; background:var(--c); }}
.s3-colh .n {{ min-width:40px; height:40px; padding:0 12px; border-radius:999px; background:#fff; font-size:21px;
              display:inline-flex; align-items:center; justify-content:center; font-variant-numeric:tabular-nums; }}
.s3-colh .r {{ margin-left:auto; font-size:18px; font-weight:600; color:#4B5563; }}
.s3-colb {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:14px; padding:2px 2px 6px; }}
.s3-empty {{ padding:28px; border-radius:16px; border:2px dashed #CDD4DC; text-align:center; font-size:20px; color:#4B5563; }}
.s3-kc {{ position:relative; display:flex; flex-direction:column; gap:12px; padding:22px 22px 18px 34px; border-radius:20px;
         background:#fff; flex-shrink:0; box-shadow:0 1px 3px rgba(16,24,40,.06); cursor:pointer;
         transition:transform .25s var(--sg-ease), box-shadow .25s var(--sg-ease); }}
.s3-kc::before {{ content:''; position:absolute; left:14px; top:22px; bottom:22px; width:6px; border-radius:999px; background:var(--a); }}
.s3-kc.top {{ box-shadow:0 10px 28px rgba(16,24,40,.12); }}
.s3-kc:hover {{ transform:translateY(-2px); box-shadow:var(--sg-shadow-up); }}
.s3-kc.sel {{ box-shadow:0 0 0 3px {B['blue']}, var(--sg-shadow-up); }}
.s3-kw .k {{ font-size:34px; font-weight:800; letter-spacing:-0.02em; line-height:1.2; }}
.s3-kw .more {{ font-size:21px; font-weight:650; color:#4B5563; margin-top:6px; }}
.s3-nm {{ display:flex; align-items:baseline; gap:10px; min-width:0; }}
.s3-nm .n {{ font-size:25px; font-weight:700; color:#111827; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-nm .d {{ font-size:19px; font-weight:500; color:#4B5563; white-space:nowrap; }}
.s3-kc-ft {{ display:flex; align-items:center; gap:10px; margin-top:4px; padding-top:14px; border-top:1px solid #EEF1F4; flex-wrap:wrap; }}
.s3-fi {{ display:flex; align-items:baseline; gap:8px; min-width:0; white-space:nowrap; }}
.s3-fi b {{ font-size:26px; font-weight:800; font-variant-numeric:tabular-nums; }}
.s3-fi span {{ font-size:19px; font-weight:500; color:#4B5563; }}
.s3-req {{ font-size:18px; font-weight:600; color:#4B5563; white-space:nowrap; }}
.s3-eqs {{ display:flex; gap:5px; }}
.s3-eqi {{ width:36px; height:36px; border-radius:10px; display:flex; align-items:center; justify-content:center;
          background:#F1F3F6; color:#A3ADB8; }}
.s3-eqi.on {{ background:var(--c); color:#fff; }}
.s3-eqi .q-icon {{ font-size:21px; }}

/* ===== 전체 사업장: 분석형 배치 ===== */
.s3-bento {{ flex:1; min-height:0; display:grid; gap:18px; grid-template-columns:1.45fr .8fr .95fr;
            grid-template-rows:minmax(0, 1fr) minmax(0, 1fr); grid-template-areas:"dept donut dist" "list list feed"; }}
.s3-bp {{ min-height:0; display:flex; flex-direction:column; padding:22px 26px; }}
.s3-bt {{ display:flex; align-items:center; gap:12px; font-size:23px; font-weight:750; margin-bottom:16px; flex-shrink:0; }}
.s3-bt .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:44px; height:44px;
                 border-radius:13px; background:{B['blue']}12; font-size:24px; color:{B['blue']}; }}
.s3-bt .r {{ margin-left:auto; font-size:17px; font-weight:500; color:#4B5563; }}
.s3-scroll {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:6px; padding-right:4px; }}
.s3-dr {{ display:grid; grid-template-columns:110px 190px 1fr 96px; align-items:center; gap:16px; padding:10px 12px;
         border-radius:14px; cursor:pointer; transition:background .2s; }}
.s3-dr:hover {{ background:var(--sg-soft); }}
.s3-dr.on {{ background:{B['blue']}10; box-shadow:inset 0 0 0 2px {B['blue']}40; }}
.s3-dr .nm {{ font-size:20px; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-sbar {{ display:flex; height:18px; border-radius:999px; overflow:hidden; background:#EDF0F3; gap:2px; }}
.s3-sbar i {{ display:block; height:100%; }}
.s3-dr .rt {{ text-align:right; font-size:18px; color:#4B5563; font-variant-numeric:tabular-nums; }}
.s3-dr .rt b {{ font-size:22px; font-weight:800; color:#1E7A34; }}
.s3-dr .rt b.bad {{ color:#C62828; }}
.s3-donut {{ flex:1; min-height:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:16px; }}
.s3-donut svg {{ width:220px; height:220px; }}
.s3-dleg {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 22px; font-size:18px; }}
.s3-dleg span {{ display:flex; align-items:center; gap:8px; }}
.s3-dleg i {{ width:12px; height:12px; border-radius:4px; background:var(--c); }}
.s3-dleg b {{ margin-left:auto; font-variant-numeric:tabular-nums; }}
.s3-hist {{ flex:1; min-height:0; display:flex; flex-direction:column; justify-content:center; gap:16px; }}
.s3-hb {{ display:grid; grid-template-columns:120px 1fr 40px; align-items:center; gap:12px; font-size:19px; }}
.s3-hb .t {{ height:22px; border-radius:8px; background:#EDF0F3; overflow:hidden; }}
.s3-hb .t i {{ display:block; height:100%; border-radius:8px; }}
.s3-hb b {{ text-align:right; font-variant-numeric:tabular-nums; }}
.s3-lr {{ display:grid; grid-template-columns:1.6fr 110px 1.4fr 160px 30px; align-items:center; gap:16px; padding:12px 14px;
         border-radius:14px; cursor:pointer; font-size:20px; transition:background .2s; flex-shrink:0; }}
.s3-lr:hover {{ background:var(--sg-soft); }}
.s3-lr .nm {{ display:flex; align-items:center; gap:10px; font-weight:700; min-width:0; }}
.s3-lr .nm span {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-lr .nm i {{ width:12px; height:12px; border-radius:50%; background:var(--c); flex-shrink:0; }}
.s3-lr .st {{ font-weight:700; color:var(--t); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-lr .st.ok {{ font-weight:500; color:#4B5563; }}
.s3-lr .tm {{ font-size:18px; color:#4B5563; text-align:right; font-variant-numeric:tabular-nums; }}
.s3-lr .q-icon {{ color:#B0B8C2; font-size:24px; }}
.s3-fd {{ display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:12px; font-size:18px; flex-shrink:0; }}
.s3-fd:nth-child(odd) {{ background:var(--sg-soft); }}
.s3-fd .tm {{ font-weight:700; font-variant-numeric:tabular-nums; width:64px; }}
.s3-fd .nm {{ flex:1; min-width:0; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-fd .st {{ font-size:16px; font-weight:700; padding:3px 12px; border-radius:999px; white-space:nowrap;
             color:var(--t); background:color-mix(in srgb, var(--c) 14%, #fff); }}

/* ===== 사업장 상세: 정보 카드 | 보고 기록 · 중요설비 ===== */
.s3-ov {{ position:fixed; left:0; top:0; width:100%; height:var(--sg-h, 100vh); z-index:2000; }}
.s3-dim {{ position:absolute; inset:0; background:rgba(17,24,39,.22); backdrop-filter:blur(6px); -webkit-backdrop-filter:blur(6px);
          animation:s3-fade .3s ease-out both; }}
.s3-drawer {{ position:absolute; top:28px; right:28px; bottom:28px; display:flex; gap:22px; }}
.s3-card {{ display:flex; flex-direction:column; min-height:0; overflow:hidden; background:{T['panel']}; border-radius:28px;
           box-shadow:0 24px 60px rgba(15,23,42,.18), 0 2px 6px rgba(15,23,42,.06); animation:s3-in .45s var(--sg-ease) both; }}
.s3-card.a {{ width:1560px; position:relative; }}
.s3-card.b {{ width:700px; animation-delay:.07s; }}
.s3-card.a.bad {{ box-shadow:0 0 0 3px color-mix(in srgb, var(--c) 35%, transparent), 0 24px 60px rgba(15,23,42,.18); }}
@keyframes s3-fade {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
@keyframes s3-in {{ from {{ transform:translateX(80px) scale(.98); opacity:0; }} to {{ transform:none; opacity:1; }} }}
.s3-glayer {{ flex:1; min-height:0; overflow-y:auto; display:flex; flex-direction:column; gap:20px; padding:30px 32px; }}
.s3-glass {{ background:var(--sg-soft); border-radius:22px; }}
.s3-top {{ display:flex; align-items:flex-start; gap:16px; }}
.s3-id {{ flex:1; display:flex; gap:30px; padding:0; background:none; }}
.s3-thumb {{ width:460px; height:300px; border-radius:20px; overflow:hidden; cursor:zoom-in; flex-shrink:0; }}
.s3-nothumb {{ width:460px; height:300px; border-radius:20px; flex-shrink:0; display:flex; flex-direction:column; align-items:center;
              justify-content:center; gap:10px; color:var(--c); background:color-mix(in srgb, var(--c) 12%, #fff); font-size:19px; }}
.s3-nothumb .q-icon {{ font-size:80px; }}
.s3-id .nm {{ font-size:46px; font-weight:800; letter-spacing:-0.02em; line-height:1.15; margin-top:6px; }}
.s3-id .ad {{ font-size:23px; color:#374151; margin-top:6px; }}
.s3-id .hint {{ font-size:18px; color:#6B7280; margin-top:4px; }}
.s3-id .meta {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
.s3-xbtn {{ margin-left:auto; }}
.s3-xbtn .q-btn {{ background:var(--sg-soft) !important; }}
.s3-alert {{ display:flex; align-items:center; gap:14px; padding:16px 24px; border-radius:18px; color:#fff; width:fit-content;
            max-width:100%; background:var(--c); box-shadow:0 10px 26px color-mix(in srgb, var(--c) 35%, transparent); }}
.s3-alert .q-icon {{ font-size:32px; }}
.s3-alert b {{ font-size:28px; font-weight:800; }}
.s3-alert span {{ font-size:20px; font-weight:500; opacity:.95; }}
.s3-gcards {{ display:grid; grid-template-columns:1fr 1fr 1.1fr; gap:16px; }}
.s3-gc {{ display:flex; flex-direction:column; gap:14px; padding:24px 26px; min-height:340px; }}
.s3-gc-t {{ display:flex; align-items:center; gap:10px; font-size:21px; font-weight:750; }}
.s3-gc-t .q-icon {{ font-size:24px; color:{B['blue']}; }}
.s3-gc-t .r {{ margin-left:auto; font-size:16px; font-weight:500; color:#4B5563; }}
.s3-big {{ font-size:40px; font-weight:800; letter-spacing:-0.02em; font-variant-numeric:tabular-nums; }}
.s3-big small {{ font-size:19px; font-weight:500; color:#4B5563; margin-left:8px; }}
.s3-bar {{ height:12px; border-radius:999px; background:rgba(0,0,0,.08); overflow:hidden; }}
.s3-bar i {{ display:block; height:100%; border-radius:999px; }}
.s3-near {{ display:flex; align-items:center; gap:10px; padding:11px 14px; border-radius:14px; background:#fff;
           cursor:pointer; font-size:19px; transition:background .2s; }}
.s3-near:hover {{ background:#fff; }}
.s3-near i {{ width:12px; height:12px; border-radius:50%; background:var(--c); flex-shrink:0; }}
.s3-near .nm {{ flex:1; min-width:0; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-near .km {{ font-size:17px; color:#4B5563; font-variant-numeric:tabular-nums; }}
.s3-eqg {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; }}
.s3-eq {{ display:flex; flex-direction:column; align-items:center; gap:2px; padding:14px 4px; border-radius:14px;
         background:#fff; font-size:17px; color:#4B5563; }}
.s3-eq .q-icon {{ font-size:30px; color:#9AA6B2; }}
.s3-eq.on {{ background:color-mix(in srgb, var(--c) 16%, #fff); color:var(--c); font-weight:700; }}
.s3-eq.on .q-icon {{ color:var(--c); }}
.s3-incrow {{ display:flex; align-items:center; gap:10px; padding:11px 14px; border-radius:14px; background:#fff;
             cursor:pointer; transition:background .2s; }}
.s3-incrow:hover {{ background:#fff; }}
.s3-incrow .ty {{ flex:1; min-width:0; font-size:19px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-incrow .sub {{ font-size:16px; color:#4B5563; white-space:nowrap; }}
.s3-gc .q-field--outlined .q-field__control {{ background:#fff !important; }}
.s3-gc .q-field__native {{ font-size:19px !important; }}
.s3-pill {{ display:inline-flex; align-items:center; gap:6px; padding:5px 14px; border-radius:999px; font-size:17px;
           font-weight:700; white-space:nowrap; width:fit-content; color:var(--t, var(--c)); background:color-mix(in srgb, var(--c) 14%, #fff); }}
.s3-card-head {{ display:flex; align-items:center; gap:12px; padding:30px 32px 10px; flex-shrink:0; }}
.s3-card-head .t {{ font-size:26px; font-weight:700; }}
.s3-card-body {{ flex:1; min-height:0; overflow-y:auto; padding:0 32px 30px; }}
.s3-dsec {{ padding:22px 0 8px; }}
.s3-dsec-t {{ display:flex; align-items:center; gap:12px; font-size:23px; font-weight:700; margin-bottom:14px; }}
.s3-dsec-t .q-icon {{ display:inline-flex !important; align-items:center; justify-content:center; width:42px; height:42px;
                     border-radius:13px; background:{B['blue']}12; font-size:23px; color:{B['blue']}; }}
.s3-dsec-t .r {{ margin-left:auto; font-size:17px; font-weight:500; color:#4B5563; }}
.s3-tl {{ position:relative; margin-top:6px; padding-left:28px; }}
.s3-tl::before {{ content:''; position:absolute; left:8px; top:10px; bottom:10px; width:2px; border-radius:999px; background:#E8EBEF; }}
.s3-tl-item {{ position:relative; padding:4px 0 18px; }}
.s3-tl-item::before {{ content:''; position:absolute; left:-26px; top:10px; width:14px; height:14px; border-radius:50%;
                      background:var(--c, #D5DAE1); border:3px solid {T['panel']}; }}
.s3-tl-text {{ font-size:20px; }}
.s3-tl-time {{ font-size:16px; color:#4B5563; margin-top:2px; font-variant-numeric:tabular-nums; }}
.s3-fac {{ padding:18px 20px; border-radius:16px; background:var(--sg-soft); display:flex; flex-direction:column; gap:6px; margin-top:8px; }}
.s3-fac-n {{ font-size:20px; font-weight:700; }}
.s3-fac-f {{ font-size:19px; }}
.s3-fac-x {{ font-size:17px; color:#4B5563; }}
.s3-photo-dlg {{ padding:14px !important; border-radius:24px !important; max-width:none !important; gap:10px !important; }}

/* 전체 사업장 v6.1: 결론 문장 · 숫자 있는 막대 · 보고 수신 */
.s3-hl {{ font-size:22px; color:#374151; margin:-4px 0 14px; flex-shrink:0; }}
.s3-hl b {{ color:#111827; font-weight:800; }}
.s3-leg {{ display:flex; flex-wrap:wrap; gap:16px; font-size:16px; color:#4B5563; margin-bottom:10px; flex-shrink:0; }}
.s3-leg span {{ display:inline-flex; align-items:center; gap:6px; }}
.s3-leg i {{ width:12px; height:12px; border-radius:4px; background:var(--c); }}
.s3-dr {{ grid-template-columns:110px 180px 1fr 120px; }}
.s3-sbar {{ height:28px; border-radius:8px; gap:2px; }}
.s3-sbar i {{ display:flex; align-items:center; justify-content:center; min-width:24px; color:#fff; font-size:15px;
             font-weight:800; font-style:normal; }}
.s3-dr .rt {{ font-size:18px; font-weight:700; text-align:right; white-space:nowrap; }}
.s3-donut .hl {{ font-size:22px; color:#374151; }}
.s3-donut .hl b {{ font-size:26px; color:#1E7A34; font-weight:800; }}
.s3-rstats {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; flex-shrink:0; }}
.s3-rs {{ padding:14px 16px; border-radius:16px; background:color-mix(in srgb, var(--c) 11%, #fff); }}
.s3-rs b {{ display:block; font-size:36px; font-weight:800; color:var(--t); font-variant-numeric:tabular-nums; line-height:1.1; }}
.s3-rs span {{ font-size:16px; font-weight:600; color:#4B5563; }}
.s3-risk {{ display:flex; align-items:center; gap:10px; padding:11px 14px; border-radius:14px; background:var(--sg-soft);
           cursor:pointer; font-size:19px; flex-shrink:0; transition:background .2s; }}
.s3-risk:hover {{ background:#E9ECF0; }}
.s3-risk i {{ width:12px; height:12px; border-radius:50%; background:var(--c); flex-shrink:0; }}
.s3-risk .nm {{ flex:1; min-width:0; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-risk .tm {{ font-size:17px; font-weight:600; color:var(--t); white-space:nowrap; }}

/* 사업장 목록 글자 */
.s3-lr {{ grid-template-columns:1.6fr 110px 1.5fr 190px 30px; gap:18px; padding:16px 18px; font-size:22px; }}
.s3-lr + .s3-lr {{ margin-top:2px; }}
.s3-lr.bad {{ background:color-mix(in srgb, var(--c) 8%, #fff); box-shadow:inset 4px 0 0 var(--c); }}
.s3-lr.bad:hover {{ background:color-mix(in srgb, var(--c) 13%, #fff); }}
.s3-lr .nm {{ font-size:23px; }}
.s3-lr .nm i {{ width:14px; height:14px; }}
.s3-lr .st {{ font-size:22px; font-weight:800; }}
.s3-lr .st.ok {{ font-size:20px; font-weight:600; color:#1E7A34; }}
.s3-lr .tm {{ font-size:19px; }}

/* 전체 사업장 v6.2: 사업단 | 사업장 목록(크게) | 전체 상태 + 보고 수신 */
.s3-bento {{ grid-template-columns:1fr 1.35fr .8fr;
            grid-template-areas:"list list donut" "list list feed"; }}
.s3-dr {{ padding:14px 12px; }}

/* 상세: 이 사업장 상황 이력 */
.s3-hx {{ display:flex; flex-direction:column; gap:10px; padding:24px 26px; }}
.s3-hrow {{ display:grid; grid-template-columns:110px 100px minmax(0,1.7fr) minmax(0,1fr) 200px; align-items:center; gap:18px;
           padding:12px 18px; border-radius:14px; background:#fff; font-size:20px; }}
.s3-hrow.open {{ cursor:pointer; box-shadow:inset 5px 0 0 var(--c); }}
.s3-hrow.open:hover {{ background:#F4F7FB; }}
.s3-hrow .t b {{ font-size:22px; font-weight:800; font-variant-numeric:tabular-nums; }}
.s3-hrow .t small {{ display:block; font-size:15px; color:#6B7280; }}
.s3-hrow .ty {{ font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-hrow .lc {{ color:#4B5563; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.s3-hrow .rs {{ text-align:right; font-weight:750; color:var(--t); white-space:nowrap; }}
.s3-hmore {{ font-size:17px; color:#6B7280; padding:2px 6px; }}

</style>
"""


# ── 도우미 ──
def scolor(st):
    return S.STATUS_COLOR.get(st, GRAY)


def dtag(dept):
    c = DEPT_COLOR.get(dept, GRAY)
    return f'<span class="s3-dtag" style="--c:{c}">{DEPT_SHORT.get(dept, dept)}</span>'


def fmt_min(m):
    if m is None:
        return '-'
    return f'{m:.0f}분' if m < 60 else f'{int(m // 60)}시간 {int(m % 60)}분'


def site_photo(sid):
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        p = config.SITE_PHOTO_DIR / f'{sid}{ext}'
        if p.exists():
            return f'/assets/sites/{sid}{ext}?v={int(p.stat().st_mtime)}'
    return None


def report_level(s):
    r = (S.now() - s['last_report']) / (config.REPORT_DELAY_HOURS * 3600)
    return r, ('over' if r >= 1 else 'soon' if r >= .75 else 'ok')


def key_words(s, st, incs):
    """핵심어 [(글자, 띠 색, 글자색)] — 자세한 내용은 화면1"""
    if incs:
        return [(short_tag(i), S.GRADE_COLOR[i['grade']], KEY_TEXT.get(i['grade'], '#333')) for i in incs]
    if st == '확인 필요':
        return [('보고 지연', '#E9A400', STATUS_TEXT['확인 필요'])]
    if st == '확인 불가':
        return [('연결 끊김', GRAY, STATUS_TEXT['확인 불가'])]
    if st == '이상':
        out = [(f'{e} {v}', EQUIP_COLOR.get(v, C['warn']), EQUIP_TEXT.get(v, '#A85400'))
               for e, v in s['equip'].items() if v != '정상']
        if s['aux']:
            out.append((s['aux'], C['warn'], '#A85400'))
        if s['report'] != '정상':
            out.append((s.get('report_note') or '이상 보고', C['warn'], '#A85400'))
        return out
    return []


def requested_at(s):
    ts = [b['ts'] for b in S.state.broadcasts
          if b.get('to', '').startswith(s['name']) and REQUEST_TEXT in b['text'] and b['ts'] > s['last_report']]
    return max(ts) if ts else None


def dist_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a['lat'], a['lng'], b['lat'], b['lng']])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def donut_svg(parts, total, big, small):
    """여러 색 도넛: parts = [(개수, 색)]"""
    r = 74
    circ = 2 * math.pi * r
    segs, off = '', 0.0
    for n, col in parts:
        if not n or not total:
            continue
        length = circ * n / total
        segs += (f'<circle cx="100" cy="100" r="{r}" fill="none" stroke="{col}" stroke-width="26" '
                 f'stroke-dasharray="{max(length - 3, 1):.1f} {circ:.1f}" stroke-dashoffset="{-off:.1f}" '
                 f'transform="rotate(-90 100 100)"/>')
        off += length
    return (f'<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="100" cy="100" r="{r}" fill="none" stroke="#EDF0F3" stroke-width="26"/>{segs}'
            f'<text x="100" y="104" text-anchor="middle" font-size="40" font-weight="800" fill="{T["text"]}">{big}</text>'
            f'<text x="100" y="132" text-anchor="middle" font-size="15" fill="#4B5563">{small}</text></svg>')


def draw():
    ui.add_head_html(CSS)
    gdata = geo.load()
    coords = gdata[1] if gdata else {}
    view = {'page': 'board', 'gu': '전체', 'dept': None, 'linked': False, 'dept_open': False, 'q': '', 'sel_dept': None}
    det = {'sid': None, 'note': '', 'ver': -1, 't': 0}
    photo = {'src': None, 'name': ''}
    refs = {}

    def counts():
        cnt = {k: 0 for k in ORDER}
        for sid in S.state.sites:
            cnt[S.site_status(sid)] += 1
        return cnt

    def match(s):
        if view['gu'] != '전체' and s['gu'] != view['gu']:
            return False
        if view['dept'] and s['dept'] != view['dept']:
            return False
        if view['linked'] and not s['linked']:
            return False
        q = view['q'].strip()
        return not q or q in s['name'] or q in s['dept'] or q in s['addr']

    def refresh_all():
        refs['ptabs'].refresh()
        refs['filters'].refresh()
        refs['depts'].refresh()
        refs['main'].refresh()

    def set_view(key, value):
        if key == 'dept':
            view['dept'] = None if view['dept'] == value else value
        elif key in ('linked', 'dept_open'):
            view[key] = not view[key]
        elif key == 'sel_dept':
            view['sel_dept'] = None if view['sel_dept'] == value else value
        else:
            view[key] = value
        refresh_all()

    def set_q(v):
        view['q'] = v or ''
        refs['filters'].refresh()
        refs['main'].refresh()

    def confirm(sid, status='정상', text=''):
        S.manual_report(sid, status, text, S.state.operator)

    def request_report(sid):
        s = S.state.sites[sid]
        p = S.staff_of(sid, '현장 담당자')
        to = f"{s['name']} " + (f"{p['name']}(현장 담당자)" if p else '담당')
        S.broadcast(f"{s['name']} {REQUEST_TEXT}", S.state.operator or '관제사', to=to)
        ui.notify(f"{s['name']} 담당자에게 보고를 요청했습니다", type='positive')

    # ── 제목 옆 페이지 전환 ──
    def build_ptabs():
        cnt = counts()
        with ui.element('div').classes('s3-ptabs'):
            for key, label, icon, n in [('board', '상황 보드', 'view_kanban', len(S.state.sites) - cnt['정상']),
                                        ('all', '전체 사업장', 'insights', len(S.state.sites))]:
                tab = ui.element('div').classes('s3-ptab' + (' on' if view['page'] == key else ''))
                tab.on('click', lambda e, k=key: set_view('page', k))
                with tab:
                    ui.icon(icon)
                    ui.label(label)
                    ui.html(f'<b>{n}</b>')

    # ── 운영 지표 줄 ──
    def build_kpi():
        cnt = counts()
        sites = list(S.state.sites.values())
        total = len(sites)
        unl = [s for s in sites if not s['linked']]
        linked = [s for s in sites if s['linked']]
        conn = sum(1 for s in linked if s['connected'])
        mean = sum(S.now() - s['last_report'] for s in unl) / len(unl) / 60 if unl else None
        n_inc = len(S.open_incidents())
        ok_mean = mean is not None and mean < config.REPORT_DELAY_HOURS * 60 * .75
        cells = [
            ('domain', B['blue'], '관제 사업장', f'{total}곳', f"정상 {cnt['정상']}곳", C['ok'], '#1E7A34'),
            ('schedule', B['sky'], '평균 보고 경과', fmt_min(mean),
             '양호' if ok_mean else '주의', C['ok'] if ok_mean else C['warn'], '#1E7A34' if ok_mean else '#A85400'),
            ('running_with_errors', '#E08A00', '보고 지연', f"{cnt['확인 필요']}곳",
             '확인 필요' if cnt['확인 필요'] else '없음', '#E9A400' if cnt['확인 필요'] else C['ok'],
             '#8A5A00' if cnt['확인 필요'] else '#1E7A34'),
            ('pending_actions', C['alarm'], '미조치 사업장', f"{cnt['미조치']}곳", f'상황 {n_inc}건',
             C['alarm'] if n_inc else C['ok'], '#C62828' if n_inc else '#1E7A34'),
            ('wifi' if conn == len(linked) else 'wifi_off', C['ok'] if conn == len(linked) else GRAY,
             '시스템 연결', f'{conn}/{len(linked)}', '정상' if conn == len(linked) else '끊김',
             C['ok'] if conn == len(linked) else GRAY, '#1E7A34' if conn == len(linked) else '#374151'),
        ]
        with ui.element('div').classes('sg-panel s3-kpi'):
            for icon, icol, label, value, badge, bcol, btext in cells:
                with ui.element('div').classes('s3-k'):
                    with ui.element('div').classes('ic').style(f'--i:{icol}'):
                        ui.icon(icon)
                    with ui.column().classes('gap-0').style('min-width:0'):
                        ui.label(label).classes('l')
                        ui.label(value).classes('v')
                    ui.label(badge).classes('b').style(f'--c:{bcol};--t:{btext}')

    # ── 필터 ──
    def build_filters():
        sites = list(S.state.sites.values())
        with ui.element('div').classes('s3-frow'):
            with ui.element('div').classes('s3-seg'):
                for g in ('전체', '서해구', '검단구'):
                    n = len(sites) if g == '전체' else sum(1 for s in sites if s['gu'] == g)
                    seg = ui.element('div').classes('on' if view['gu'] == g else '')
                    seg.on('click', lambda e, x=g: set_view('gu', x))
                    with seg:
                        ui.label(g)
                        ui.html(f'<b>{n}</b>')
            dept_btn = ui.element('div').classes('s3-fc' + (' on' if view['dept'] else ''))
            dept_btn.on('click', lambda e: set_view('dept_open', None))
            with dept_btn:
                ui.label(view['dept'] or '사업단 전체')
                ui.icon('expand_less' if view['dept_open'] else 'expand_more')
            lk = ui.element('div').classes('s3-fc' + (' on' if view['linked'] else ''))
            lk.on('click', lambda e: set_view('linked', None))
            with lk:
                ui.icon('sensors')
                ui.label('AI·경보 연계만')
            if view['page'] == 'board':
                shown = sum(1 for s in sites if match(s) and S.site_status(s['id']) != '정상')
            else:
                shown = sum(1 for s in sites if match(s))
            ui.label(f'표시 {shown}곳').classes('s3-count')

    def build_depts():
        if not view['dept_open']:
            return
        sites = list(S.state.sites.values())
        with ui.element('div').classes('s3-depts'):
            for d in config.DEPTS:
                n = sum(1 for s in sites if s['dept'] == d)
                if not n:
                    continue
                chip = ui.element('div').classes('s3-fc' + (' on' if view['dept'] == d else ''))
                chip.on('click', lambda e, x=d: set_view('dept', x))
                with chip:
                    ui.label(d)
                    ui.label(str(n)).style('opacity:.6')

    # ── 상황 보드 ──
    def foot_info(s, incs):
        if incs:
            first = min(i['start'] for i in incs)
            late = S.now() - first >= 3600
            return S.ago(first), '경과', '#C62828' if late else T['text']
        if s['linked']:
            return ('실시간', '설비 신호 수신', '#1E7A34') if s['connected'] else ('끊김', '설비 신호', '#374151')
        if S.report_overdue(s):
            return S.hm(s['last_report']), '이후 보고 없음', STATUS_TEXT['확인 필요']
        return f"{S.ago(s['last_report'])} 전", '마지막 보고', T['text']

    def site_card(s, first):
        sid = s['id']
        st = S.site_status(sid)
        incs = sorted(S.open_incidents(sid), key=lambda i: (S.GRADE_RANK[i['grade']], i['start']))
        words = key_words(s, st, incs)
        accent = words[0][1] if words else scolor(st)
        card = ui.element('div').classes('s3-kc' + (' top' if first else '') + (' sel' if det['sid'] == sid else '')) \
            .style(f'--a:{accent}')
        card.on('click', lambda e, x=sid: open_detail(x))
        with card:
            if words:
                with ui.element('div').classes('s3-kw'):
                    ui.label(words[0][0]).classes('k').style(f'color:{words[0][2]}')
                    if len(words) > 1:
                        ui.label('+ ' + ' · '.join(w for w, _, _ in words[1:])).classes('more')
            with ui.element('div').classes('s3-nm'):
                ui.label(s['name']).classes('n')
                ui.label(s['dept']).classes('d')
            with ui.element('div').classes('s3-kc-ft'):
                value, label, col = foot_info(s, incs)
                ui.html(f'<div class="s3-fi"><b style="color:{col}">{value}</b><span>{label}</span></div>')
                ui.space()
                if s['linked']:
                    with ui.element('div').classes('s3-eqs'):
                        for e, ic in config.EQUIPMENT.items():
                            v = s['equip'].get(e, '정상') if s['connected'] else '확인 불가'
                            box = ui.element('div').classes('s3-eqi' + (' on' if v != '정상' else '')) \
                                .style(f'--c:{EQUIP_COLOR.get(v, GRAY)}').props(f'title="{e} · {v}"')
                            with box:
                                ui.icon(ic)
                if not incs and S.report_overdue(s):
                    req = requested_at(s)
                    if req:
                        ui.label(f'요청 {S.hm(req)}').classes('s3-req')
                    else:
                        ui.button('보고 요청', icon='campaign').props('unelevated no-caps') \
                            .style('background:#fff !important;color:#8A5A00 !important;font-size:18px;font-weight:700;'
                                   'padding:5px 16px;box-shadow:inset 0 0 0 1.5px #E9C46A') \
                            .on('click.stop', lambda e, x=sid: request_report(x))
                    ui.button('보고 확인').props('unelevated no-caps') \
                        .style('background:#FFEDC2 !important;color:#7A4E00 !important;font-size:18px;'
                               'font-weight:700;padding:5px 18px') \
                        .on('click.stop', lambda e, x=sid: confirm(x))
                elif not incs and s['report'] != '정상':
                    ui.button('정상 확인').props('unelevated no-caps') \
                        .style('background:#DDF1E2 !important;color:#1E6B30 !important;font-size:18px;'
                               'font-weight:700;padding:5px 18px') \
                        .on('click.stop', lambda e, x=sid: confirm(x))

    def col_sort(st):
        if st == '미조치':
            return lambda s: (min(S.GRADE_RANK[i['grade']] for i in S.open_incidents(s['id'])),
                              min(i['start'] for i in S.open_incidents(s['id'])))
        if st == '확인 필요':
            return lambda s: s['last_report']
        return lambda s: (not s['linked'], s['name'])

    def build_board():
        sites = [s for s in S.state.sites.values() if match(s)]
        with ui.element('div').classes('s3-board'):
            for st, note in COLS:
                col_sites = sorted([s for s in sites if S.site_status(s['id']) == st], key=col_sort(st))
                with ui.element('div').classes('s3-col'):
                    with ui.element('div').classes('s3-colh').style(f'--c:{scolor(st)}'):
                        ui.element('span').classes('dot')
                        ui.label(st)
                        ui.label(str(len(col_sites))).classes('n')
                        ui.label(note).classes('r')
                    with ui.element('div').classes('s3-colb'):
                        if not col_sites:
                            ui.label('해당 사업장 없음').classes('s3-empty')
                        for k, s in enumerate(col_sites):
                            site_card(s, k == 0)

    # ── 전체 사업장: 분석형 배치 ──
    def bt(icon, text, right=''):
        with ui.element('div').classes('s3-bt'):
            ui.icon(icon)
            ui.label(text)
            if right:
                ui.label(right).classes('r')

    def panel_depts(sites):
        """어느 사업단에 확인할 사업장이 있나 — 문제 많은 사업단이 위로"""
        data = []
        for d in config.DEPTS:
            ds = [s for s in sites if s['dept'] == d]
            if ds:
                cnt = {k: sum(1 for s in ds if S.site_status(s['id']) == k) for k in ORDER}
                data.append((d, ds, cnt, len(ds) - cnt['정상']))
        data.sort(key=lambda x: (-x[3], config.DEPTS.index(x[0])))
        worst = data[0] if data and data[0][3] else None
        with ui.element('div').classes('sg-panel s3-bp').style('grid-area:dept'):
            bt('stacked_bar_chart', '사업단별 상태', '누르면 아래 목록이 그 사업단으로 바뀝니다')
            ui.html(f'<div class="s3-hl"><b>{worst[0]}</b>에 확인할 사업장이 가장 많아요 ({worst[3]}곳)</div>'
                    if worst else '<div class="s3-hl"><b>모든 사업단</b>이 정상이에요</div>')
            ui.html('<div class="s3-leg">' + ''.join(f'<span><i style="--c:{scolor(k)}"></i>{k}</span>' for k in LEGEND)
                    + '<span>· 막대 안 숫자 = 사업장 수</span></div>')
            with ui.element('div').classes('s3-scroll'):
                for d, ds, cnt, bad in data:
                    segs = ''.join(f'<i style="flex:{cnt[k]};background:{scolor(k)}" title="{k} {cnt[k]}곳">{cnt[k]}</i>'
                                   for k in ORDER if cnt[k])
                    row = ui.element('div').classes('s3-dr' + (' on' if view['sel_dept'] == d else ''))
                    row.on('click', lambda e, x=d: set_view('sel_dept', x))
                    with row:
                        ui.html(dtag(d))
                        ui.label(d).classes('nm')
                        ui.html(f'<div class="s3-sbar">{segs}</div>')
                        ui.html(f'<div class="rt" style="color:#C62828">문제 {bad}곳</div>' if bad
                                else '<div class="rt" style="color:#1E7A34">모두 정상</div>')

    def panel_donut(sites):
        """전체 사업장 상태 비율"""
        cnt = {k: sum(1 for s in sites if S.site_status(s['id']) == k) for k in ORDER}
        total = len(sites)
        pct = round(cnt['정상'] / total * 100) if total else 0
        with ui.element('div').classes('sg-panel s3-bp').style('grid-area:donut'):
            bt('donut_large', '전체 상태')
            with ui.element('div').classes('s3-donut'):
                ui.html(f'<div class="hl">{total}곳 중 <b>{cnt["정상"]}곳</b> 정상</div>')
                ui.html(donut_svg([(cnt[k], scolor(k)) for k in LEGEND], total, f'{pct}%', '정상 비율'))
                with ui.element('div').classes('s3-dleg'):
                    for k in LEGEND:
                        ui.html(f'<span><i style="--c:{scolor(k)}"></i>{k}<b>{cnt[k]}곳</b></span>')

    def panel_reports(sites):
        """정기 보고는 제때 들어오고 있나 (미연계 사업장)"""
        unl = [s for s in sites if not s['linked']]
        late = sorted([s for s in unl if S.report_overdue(s)], key=lambda s: s['last_report'])
        soon = sorted([s for s in unl if not S.report_overdue(s) and report_level(s)[1] == 'soon'],
                      key=lambda s: s['last_report'])
        ok = len(unl) - len(late) - len(soon)
        with ui.element('div').classes('sg-panel s3-bp').style('grid-area:dist'):
            bt('schedule', '정기 보고 수신', f'미연계 {len(unl)}곳 · 사업장이 직접 보고')
            if late:
                hl = f'<b>{len(late)}곳</b>에서 보고가 들어오지 않았어요'
            elif soon:
                hl = f'<b>{len(soon)}곳</b>이 곧 보고가 늦어질 수 있어요'
            else:
                hl = '<b>모든 사업장</b>의 보고가 제때 들어오고 있어요'
            ui.html(f'<div class="s3-hl">{hl}</div>')
            with ui.element('div').classes('s3-rstats'):
                for label, n, col, tcol in [('제때 수신', ok, C['ok'], '#1E7A34'),
                                            ('지연 임박', len(soon), '#F2B33D', '#9A6A00'),
                                            ('보고 지연', len(late), '#E08A00', '#8A5A00')]:
                    ui.html(f'<div class="s3-rs" style="--c:{col};--t:{tcol}"><b>{n}</b><span>{label}</span></div>')
            with ui.element('div').classes('s3-scroll').style('margin-top:14px'):
                for s in late + soon:
                    is_late = S.report_overdue(s)
                    col, tcol = ('#E08A00', '#8A5A00') if is_late else ('#F2B33D', '#9A6A00')
                    text = f"{S.hm(s['last_report'])} 이후 보고 없음" if is_late else f"{S.ago(s['last_report'])} 전 보고"
                    row = ui.element('div').classes('s3-risk').style(f'--c:{col};--t:{tcol}')
                    row.on('click', lambda e, x=s['id']: open_detail(x))
                    with row:
                        ui.element('i')
                        ui.label(s['name']).classes('nm')
                        ui.label(text).classes('tm')

    def panel_list(sites):
        sel = view['sel_dept']
        rows = [s for s in sites if not sel or s['dept'] == sel]
        rows.sort(key=lambda s: (ORDER.index(S.site_status(s['id'])), s['name']))
        with ui.element('div').classes('sg-panel s3-bp').style('grid-area:list'):
            bt('list', f'{sel} 사업장' if sel else '사업장 목록', f'{len(rows)}곳 · 문제 있는 곳 먼저 · 누르면 상세')
            with ui.element('div').classes('s3-scroll'):
                for s in rows:
                    st = S.site_status(s['id'])
                    incs = S.open_incidents(s['id'])
                    words = key_words(s, st, incs)
                    text = (words[0][0] + (f' 외 {len(words) - 1}' if len(words) > 1 else '')) if words else '정상'
                    when = '실시간 수신' if s['linked'] else f"{S.ago(s['last_report'])} 전 보고"
                    r = ui.element('div').classes('s3-lr' + (' bad' if st != '정상' else '')) \
                        .style(f'--c:{scolor(st)};--t:{STATUS_TEXT.get(st)}')
                    r.on('click', lambda e, x=s['id']: open_detail(x))
                    with r:
                        ui.html(f'<div class="nm"><i></i><span>{s["name"]}</span></div>')
                        ui.html(dtag(s['dept']))
                        ui.label(text).classes('st' + (' ok' if st == '정상' else ''))
                        ui.label(when).classes('tm')
                        ui.icon('chevron_right')

    def panel_feed(sites):
        names = {s['id'] for s in sites}
        items = []
        for s in S.state.sites.values():
            if s['id'] not in names:
                continue
            for r in s.get('report_log', []):
                items.append((r['ts'], s['name'], r['status'], REPORT_COLOR.get(r['status'], GRAY)))
        for b in S.state.broadcasts:
            if REQUEST_TEXT in b['text']:
                items.append((b['ts'], b.get('to', '').split(' ')[0], '보고 요청', '#E9A400'))
        items.sort(key=lambda x: -x[0])
        with ui.element('div').classes('sg-panel s3-bp').style('grid-area:feed'):
            bt('sensors', '실시간 보고 수신', '최근 30건')
            with ui.element('div').classes('s3-scroll'):
                if not items:
                    ui.label('수신 기록 없음').classes('s3-empty')
                for ts, name, status, col in items[:30]:
                    text = '정상 보고' if status == '정상' else ('이상 보고' if status == '이상' else status)
                    tcol = {'정상': '#1E7A34', '이상': '#A85400'}.get(status, '#8A5A00')
                    ui.html(f'<div class="s3-fd"><span class="tm">{S.hm(ts)}</span><span class="nm">{name}</span>'
                            f'<span class="st" style="--c:{col};--t:{tcol}">{text}</span></div>')

    def build_all():
        sites = [s for s in S.state.sites.values() if match(s)]
        with ui.element('div').classes('s3-bento'):
            panel_donut(sites)
            panel_list(sites)
            panel_feed(sites)

    def build_main():
        if view['page'] == 'board':
            build_board()
        else:
            build_all()

    # ── 사업장 상세: 카드 ──
    def alert_strip(s, st, incs):
        if incs:
            top = incs[0]
            more = f' · 외 {len(incs) - 1}건' if len(incs) > 1 else ''
            return (S.GRADE_COLOR[top['grade']], 'warning', f"{top['grade']} · {short_tag(top)}",
                    f"{top['type']} · {top['loc']} · {top['stage']} · {S.ago(top['start'])} 경과{more}")
        if st == '확인 필요':
            req = requested_at(s)
            return ('#D99100', 'schedule', '보고 지연',
                    f"{S.hm(s['last_report'])} 이후 보고 없음" + (f' · {S.hm(req)} 보고 요청함' if req else ''))
        if st == '확인 불가':
            return (GRAY, 'wifi_off', '연결 끊김', 'AI·경보 시스템 신호를 받을 수 없습니다')
        if st == '이상':
            words = key_words(s, st, incs)
            return (C['warn'], 'report', words[0][0] if words else '이상',
                    ' · '.join(w for w, _, _ in words[1:]) or '관제사 확인 필요')
        return None

    def gc_report(s):
        """정기 보고 카드 (미연계)"""
        sid = s['id']
        r, lv = report_level(s)
        with ui.element('div').classes('s3-glass s3-gc'):
            with ui.element('div').classes('s3-gc-t'):
                ui.icon('schedule')
                ui.label('정기 보고')
                ui.label(f"마지막 {S.md_hm(s['last_report'])}").classes('r')
            ui.html(f'<div class="s3-big" style="color:{BAR_TEXT[lv] if lv != "ok" else T["text"]}">'
                    f'{S.ago(s["last_report"])}<small>전 보고</small></div>')
            ui.html(f'<div class="s3-bar"><i style="width:{min(r, 1) * 100:.0f}%;background:{BAR_COLOR[lv]}"></i></div>')
            if s['report'] != '정상':
                ui.html(f'<span class="s3-pill" style="--c:{C["warn"]};--t:#A85400">현재 이상 · '
                        f'{s.get("report_note") or s["report"]}</span>')
            with ui.row().classes('gap-2').style('margin-top:auto'):
                if S.report_overdue(s) and not requested_at(s):
                    ui.button('보고 요청', icon='campaign', on_click=lambda: request_report(sid)).props('unelevated no-caps') \
                        .style('background:#FFEDC2 !important;color:#7A4E00 !important;font-size:18px;font-weight:700')
                ui.button('정상 확인', on_click=lambda: confirm(sid)).props('unelevated no-caps') \
                    .style(f"background:{C['ok']} !important;color:#fff !important;font-size:18px;font-weight:700")

    def gc_equip(s):
        """설비 신호 카드 (AI·경보 연계)"""
        with ui.element('div').classes('s3-glass s3-gc'):
            with ui.element('div').classes('s3-gc-t'):
                ui.icon('sensors')
                ui.label('설비 신호')
                ui.label('실시간 수신' if s['connected'] else '연결 끊김').classes('r')
            with ui.element('div').classes('s3-eqg'):
                for e, icon in config.EQUIPMENT.items():
                    v = s['equip'].get(e, '정상') if s['connected'] else '확인 불가'
                    with ui.element('div').classes('s3-eq' + (' on' if v != '정상' else '')) \
                            .style(f'--c:{EQUIP_COLOR.get(v, GRAY)}'):
                        ui.icon(icon)
                        ui.label(e)
                        ui.label(v).style('font-size:15px')
            if s['aux']:
                ui.html(f'<span class="s3-pill" style="--c:{C["warn"]};--t:#A85400">보조 설비 · {s["aux"]}</span>')

    def gc_near(s):
        sid = s['id']
        c = coords.get(sid)
        with ui.element('div').classes('s3-glass s3-gc'):
            with ui.element('div').classes('s3-gc-t'):
                ui.icon('near_me')
                ui.label('주변 사업장')
                ui.label('누르면 이동').classes('r')
            if not c:
                ui.label('위치 정보 없음').style('font-size:18px;color:#4B5563')
                return
            near = sorted((dist_km(c, coords[o]), o) for o in S.state.sites if o != sid and o in coords)[:4]
            for d, o in near:
                ost = S.site_status(o)
                row = ui.element('div').classes('s3-near').style(f'--c:{scolor(ost)}')
                row.on('click', lambda e, x=o: open_detail(x))
                with row:
                    ui.element('i')
                    ui.label(S.state.sites[o]['name']).classes('nm')
                    ui.label(f'{d:.1f}km').classes('km')

    def gc_action(s, incs):
        sid = s['id']
        with ui.element('div').classes('s3-glass s3-gc'):
            if incs:
                with ui.element('div').classes('s3-gc-t'):
                    ui.icon('pending_actions')
                    ui.label('미조치 상황')
                    ui.label('누르면 화면1에 표시').classes('r')
                for inc in incs:
                    row = ui.element('div').classes('s3-incrow')
                    row.on('click', lambda e, i=inc['id']: S.select_incident(i))
                    with row:
                        ui.html(grade_html(inc['grade']))
                        ui.label(f"{inc['type']} · {inc['loc']}").classes('ty')
                        ui.html(step_html(inc['stage']))
                return

            def report_issue():
                text = (det['note'] or '').strip()
                if not text:
                    ui.notify('이상 내용을 입력하세요', type='warning')
                    return
                confirm(sid, '이상', text)
                det['note'] = ''
                glass.refresh()

            with ui.element('div').classes('s3-gc-t'):
                ui.icon('edit_note')
                ui.label('이상 보고 입력')
                ui.label('전화 확인 후 기록').classes('r')
            inp = ui.textarea(placeholder='예: 출입문 개폐 불량, 천장 누수 흔적', value=det['note']) \
                .props('outlined autogrow').classes('w-full')
            inp.on_value_change(lambda e: det.__setitem__('note', e.value))
            ui.button('이상 보고 등록', on_click=report_issue).props('unelevated no-caps') \
                .style(f"background:{C['warn']} !important;color:#fff !important;font-size:18px;font-weight:700;"
                       f"margin-top:auto;align-self:flex-start")

    def gc_history(sid):
        """이 사업장 금일·전일 상황 이력 (반복 발생 확인). 처리 중인 건은 누르면 화면1에 표시"""
        rows = sorted([i for i in S.state.incidents + S.state.history if i['site'] == sid],
                      key=lambda i: -i['start'])
        n_today = sum(1 for i in rows if i['id'] > 0)
        with ui.element('div').classes('s3-glass s3-hx'):
            with ui.element('div').classes('s3-gc-t'):
                ui.icon('history')
                ui.label('이 사업장 상황 이력')
                ui.label(f'금일 {n_today}건 · 전일 {len(rows) - n_today}건 · 처리 중인 건은 누르면 화면1에 표시').classes('r')
            if not rows:
                ui.label('금일·전일 접수된 상황 없음').style('font-size:20px;color:#4B5563;padding:8px 4px')
                return
            for inc in rows[:6]:
                closed = S.is_closed(inc)
                if closed:
                    text, tcol = ('오경보 종결', '#4B5563') if inc.get('false_alarm') else ('종결', '#1E7A34')
                elif S.needs_report(inc):
                    text, tcol = '보고 미작성', '#1F5F95'
                else:
                    text, tcol = f"처리 중 · {inc['stage']}", '#C62828'
                row = ui.element('div').classes('s3-hrow' + ('' if closed else ' open')) \
                    .style(f"--c:{S.GRADE_COLOR[inc['grade']]};--t:{tcol}")
                if not closed:
                    row.on('click', lambda e, i=inc['id']: S.select_incident(i))
                with row:
                    ui.html(f'<div class="t"><b>{S.hm(inc["start"])}</b>'
                            f'<small>{"오늘" if inc["id"] > 0 else "어제"}</small></div>')
                    ui.html(grade_html(inc['grade']))
                    ui.label(inc['type'] + (f" · 총 {inc['repeat']}회" if inc['repeat'] >= 2 else '')).classes('ty')
                    ui.label(inc['loc']).classes('lc')
                    ui.label(text).classes('rs')
            if len(rows) > 6:
                ui.label(f'외 {len(rows) - 6}건 · 전체는 화면1 종결 기록').classes('s3-hmore')

    @ui.refreshable
    def glass():
        sid = det['sid']
        det['ver'], det['t'] = S.state.version, S.now()
        if not sid or sid not in S.state.sites:
            return
        s = S.state.sites[sid]
        st = S.site_status(sid)
        incs = sorted(S.open_incidents(sid), key=lambda i: (S.GRADE_RANK[i['grade']], i['start']))
        dcol = DEPT_COLOR.get(s['dept'], GRAY)
        with ui.element('div').classes('s3-glayer'):
            with ui.element('div').classes('s3-top'):
                with ui.element('div').classes('s3-id'):
                    src = site_photo(sid)
                    if src:
                        img = ui.image(src).props('fit=cover').classes('s3-thumb')
                        img.on('click', lambda e, x=src, n=s['name']: open_photo(x, n))
                    else:
                        with ui.element('div').classes('s3-nothumb').style(f'--c:{dcol}'):
                            ui.icon('apartment')
                            ui.label('사진 준비 중')
                    sel_inc = S.get_incident(S.state.selected_incident) if S.state.selected_incident else None
                    with ui.column().classes('gap-0').style('min-width:0;flex:1'):
                        with ui.row().classes('items-center gap-3 no-wrap'):
                            ui.html(f'<span class="sg-dot" style="--c:{scolor(st)};color:{STATUS_TEXT[st]};'
                                    f'font-size:24px">{st}</span>')
                            if sel_inc and sel_inc['site'] == sid:
                                ui.html(f'<span class="s3-pill" style="--c:{B["blue"]};font-size:19px">화면1 선택</span>')
                        ui.label(s['name']).classes('nm')
                        ui.label(config.full_addr(s)).classes('ad')
                        with ui.element('div').classes('meta'):
                            ui.html(dtag(s['dept']))
                            ui.html(f'<span class="s3-pill" style="--c:{B["sky"]};font-size:18px">'
                                    f"{s['gu']}</span>")
                            ui.html(f'<span class="s3-pill" style="--c:{C["ok"] if s["linked"] else GRAY};font-size:18px">'
                                    f"AI·경보 {'연계' if s['linked'] else '미연계'}</span>")
                        ui.label('위치는 화면2 지도에 표시' + (' · 사진을 누르면 크게 보기' if src else '')).classes('hint')
                with ui.element('div').classes('s3-xbtn'):
                    ui.button(icon='close', on_click=close_detail).props('flat round').tooltip('닫기 (Esc)')
            al = alert_strip(s, st, incs)
            if al:
                col, icon, head, sub = al
                ui.html(f'<div class="s3-alert" style="--c:{col}"><i class="material-icons q-icon">{icon}</i>'
                        f'<b>{head}</b><span>{sub}</span></div>')
            with ui.element('div').classes('s3-gcards'):
                if s['linked']:
                    gc_equip(s)
                else:
                    gc_report(s)
                gc_near(s)
                gc_action(s, incs)
            gc_history(sid)

    @ui.refreshable
    def side():
        sid = det['sid']
        if not sid or sid not in S.state.sites:
            return
        s = S.state.sites[sid]
        if not s['linked']:
            with ui.element('div').classes('s3-dsec'):
                log = s.get('report_log', [])
                with ui.element('div').classes('s3-dsec-t'):
                    ui.icon('history')
                    ui.label('보고 기록')
                    ui.label(f'최근 {min(len(log), 8)}건').classes('r')
                if not log:
                    ui.label('기록 없음').style('font-size:20px;color:#4B5563')
                with ui.element('div').classes('s3-tl'):
                    for r in reversed(log[-8:]):
                        col = REPORT_COLOR.get(r['status'], GRAY)
                        with ui.element('div').classes('s3-tl-item').style(f'--c:{col}'):
                            ui.html(f'<div class="s3-tl-text"><b style="color:{col}">{r["status"]}</b> · {r["text"]}</div>')
                            ui.label(f"{S.md_hm(r['ts'])} · {r['by']}").classes('s3-tl-time')
        with ui.element('div').classes('s3-dsec'):
            facs = S.state.facilities.get(sid, [])
            with ui.element('div').classes('s3-dsec-t'):
                ui.icon('handyman')
                ui.label('중요설비 · 중점관리사항')
            if not facs:
                ui.label('등록된 설비 없음').style('font-size:20px;color:#4B5563')
            for f in facs:
                with ui.element('div').classes('s3-fac'):
                    ui.label(', '.join(f['names'])).classes('s3-fac-n')
                    ui.label(f['focus'] or '-').classes('s3-fac-f')
                    if f['note']:
                        ui.label(f['note']).classes('s3-fac-x')

    def update_card():
        sid = det['sid']
        if not sid:
            return
        st = S.site_status(sid)
        card_a.classes(remove='bad')
        if st != '정상':
            card_a.classes(add='bad')
        card_a.style(f'--c:{scolor(st)}')

    def open_detail(sid):
        if det['sid'] != sid:
            det['note'] = ''
        det['sid'] = sid
        ov.set_visibility(True)
        update_card()
        glass.refresh()
        side.refresh()
        refs['main'].refresh()
        if S.state.selected_site != sid:             # 화면2 지도도 이 사업장으로 이동
            S.select_site(sid)

    def close_detail():
        det['sid'], det['note'] = None, ''
        ov.set_visibility(False)
        refs['main'].refresh()

    def sync_detail():
        if not det['sid'] or det['note']:
            return
        if S.state.version != det['ver'] or S.now() - det['t'] >= 30:
            update_card()
            glass.refresh()
            side.refresh()

    # ── 사진 크게 보기 ──
    @ui.refreshable
    def photo_view():
        if photo['src']:
            ui.label(photo['name']).style('font-size:24px;font-weight:700;padding:4px 8px')
            ui.image(photo['src']).props('fit=contain').style('width:1600px;max-height:1100px;border-radius:16px')

    def open_photo(src, name):
        photo.update(src=src, name=name)
        photo_view.refresh()
        photo_dlg.open()

    # ── 화면1 연동 ──
    follow = {'seq': None}

    def follow_selection():
        """화면1 선택 → 사업장 상세 열기 (같은 사업장을 다시 눌러도 열림, 화면3을 늦게 열어도 선택된 사업장 표시)"""
        seq = getattr(S.state, 'select_seq', 0)
        if seq == follow['seq']:
            return
        first = follow['seq'] is None
        follow['seq'] = seq
        sel = S.state.selected_site
        if first and not sel:
            return
        if sel and sel in S.state.sites:
            open_detail(sel)
        elif det['sid']:
            close_detail()

    def on_key(e):
        if e.key.name == 'Escape' and e.action.keydown and det['sid']:
            close_detail()

    # ── 화면 배치 ──
    with screen_root():
        with header('사업장별 현황', left=lambda: refs.__setitem__('ptabs', live(build_ptabs, every=30))):
            clock()
        with ui.element('div').classes('sg-body'):
            live(build_kpi, every=30)
            with ui.row().classes('w-full items-center no-wrap gap-4'):
                refs['filters'] = live(build_filters, every=30)
                ui.space()
                with ui.input(placeholder='사업장 · 사업단 · 주소 검색').props('outlined clearable') \
                        .classes('s3-search') as qi:
                    with qi.add_slot('prepend'):
                        ui.icon('search')
                qi.on_value_change(lambda e: set_q(e.value))
            refs['depts'] = live(build_depts)
            refs['main'] = live(build_main, every=30)

    # 사업장 상세 (사업장 정보 카드 | 보고 기록 · 중요설비)
    ov = ui.element('div').classes('s3-ov')
    ov.set_visibility(False)
    with ov:
        ui.element('div').classes('s3-dim').on('click', lambda e: close_detail())
        with ui.element('div').classes('s3-drawer'):
            card_a = ui.element('div').classes('s3-card a')
            with card_a:
                glass()
            with ui.element('div').classes('s3-card b'):
                with ui.element('div').classes('s3-card-head'):
                    ui.icon('fact_check').classes('sg-ico').style('font-size:30px')
                    ui.label('보고 기록 · 중요설비').classes('t')
                with ui.element('div').classes('s3-card-body'):
                    side()

    with ui.dialog() as photo_dlg, ui.card().classes('s3-photo-dlg'):
        photo_view()

    ui.keyboard(on_key=on_key)
    ui.timer(1, sync_detail)
    ui.timer(0.3, follow_selection)