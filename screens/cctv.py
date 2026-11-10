"""화면5·6 공통: CCTV 타일, 실시간(HLS)·녹화(mp4) 영상 재생, 분할 화면
- 분할 화면(화면5 평시·화면6): ITS 실시간 영상만. 연결 전·키 없음이면 '연결 대기' 안내
- 녹화 영상: 화면5 사고 화면에서만 사용"""
import json
import math
from pathlib import Path

from nicegui import ui

import config
import its
from screens import T

ASSETS = config.BASE / 'assets'
VIDEO_DIR = ASSETS / 'videos'
IMAGE_DIR = ASSETS / 'images'

HEAD = """
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.15/dist/hls.min.js"></script>
<script>
window.sgPlay = function (id, url, tries) {          // 실시간(HLS) 영상 연결 (서버 중계 /hls 경유)
  tries = tries || 0;
  const v = document.getElementById('c' + id) ||
            (typeof getHtmlElement === 'function' ? getHtmlElement(id) : null);
  if (!v || !window.Hls) {
    if (tries < 50) setTimeout(() => window.sgPlay(id, url, tries + 1), 100);
    else console.warn('[CCTV] 영상 요소 또는 hls.js 없음', id);
    return;
  }
  const tile = v.closest('.cc-tile');
  const fail = (why) => { console.warn('[CCTV] 재생 실패', why, url); if (tile) tile.classList.add('cc-nosignal'); };
  const src = '/hls?u=' + encodeURIComponent(url);
  if (Hls.isSupported()) {
    const h = new Hls({ liveDurationInfinity: true });
    h.loadSource(src); h.attachMedia(v); v._hls = h;
    h.on(Hls.Events.MANIFEST_PARSED, () => v.play().catch(() => {}));
    h.on(Hls.Events.ERROR, (e, d) => { if (d.fatal) fail(d.details); });
  } else { v.src = src; v.play().catch(() => {}); }
  setTimeout(() => { if (v.isConnected && v.readyState < 2) fail('10초 내 재생 시작 안 됨'); }, 10000);
};
window.sgStopAll = function () {                      // 순환 전 이전 연결 정리
  document.querySelectorAll('video').forEach(v => { if (v._hls) { v._hls.destroy(); v._hls = null; } });
};
setInterval(() => {                                    // 영상 위 시각
  const t = new Date().toLocaleString('sv-SE').replace(/-/g, '.');
  document.querySelectorAll('.cc-clock').forEach(e => e.textContent = t);
}, 1000);
</script>
"""

CSS = f"""
<style>
.cc-grid {{ flex:1; min-height:0; display:grid; gap:14px; }}
.cc-tile {{ position:relative; background:#0B0F14; border-radius:12px; overflow:hidden; min-height:0; }}
.cc-video {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
.cc-video.local {{ filter:grayscale(.35) contrast(1.1) brightness(.95); }}
.cc-vignette {{ position:absolute; inset:0; pointer-events:none;
               background:radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,.45) 100%); }}
.cc-top {{ position:absolute; left:0; right:0; top:0; padding:12px 18px; display:flex; align-items:center; gap:12px;
          background:linear-gradient(rgba(0,0,0,.7), transparent); color:#fff; }}
.cc-name {{ font-size:30px; font-weight:900; text-shadow:0 1px 3px rgba(0,0,0,.6);
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.cc-badge {{ display:flex; align-items:center; gap:6px; padding:3px 12px; border-radius:6px;
            font-size:18px; font-weight:700; color:#fff; flex-shrink:0; }}
.cc-live {{ background:#E5383B; }}
.cc-rec {{ background:rgba(0,0,0,.55); border:1px solid rgba(255,255,255,.4); }}
.cc-wait {{ background:#6B7280; }}
.cc-dot {{ width:10px; height:10px; border-radius:50%; background:#fff; animation:cc-blink 1s steps(2,start) infinite; }}
@keyframes cc-blink {{ 50% {{ opacity:0; }} }}
.cc-bottom {{ position:absolute; left:0; right:0; bottom:0; padding:10px 18px; display:flex; align-items:center;
             color:#fff; font-size:19px; background:linear-gradient(transparent, rgba(0,0,0,.65)); }}
.cc-clock {{ font-family:Consolas,monospace; margin-left:auto; }}
.cc-nosig {{ display:none; position:absolute; inset:0; align-items:center; justify-content:center;
            color:#9AA4B2; font-size:28px; }}
.cc-nosignal .cc-nosig {{ display:flex; }}
.cc-nosignal .cc-video {{ display:none; }}
.cc-offline {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center;
              justify-content:center; gap:10px; color:#9AA4B2; font-size:26px; text-align:center;
              background-size:cover; background-position:center; }}
.cc-offline.img::before {{ content:''; position:absolute; inset:0; background:rgba(11,15,20,.55); }}
.cc-offline > * {{ position:relative; }}
.cc-empty {{ display:flex; align-items:center; justify-content:center; color:#6B7280; font-size:26px; }}
.cc-note {{ font-size:18px; color:{T['muted']}; flex-shrink:0; }}
</style>
"""


def video_ok(file):
    return bool(file) and (VIDEO_DIR / file).exists()


def signature():
    """평시 영상 목록이 바뀌었는지 판단용 (ITS 연결·주소 갱신 시 값이 바뀜)"""
    return (len(its.data['cams']), its.data['updated'])


def sources(part=None):
    """분할 화면 영상: ITS 실시간만.
    part='a'(화면6)·'b'(화면5)로 나누면 서로 겹치지 않음. 1대뿐이면 둘 다 그 1대를 표시"""
    cams = its.data['cams']
    if part and len(cams) >= 2:
        cams = cams[0::2] if part == 'a' else cams[1::2]
    return [{'name': c['name'], 'url': c['url'], 'sub': f"{c['kind']} · 국가교통정보센터"}
            for c in cams]


def event_video(inc):
    """화면5 사고 화면용 녹화 영상: 상황 유형(우선) 또는 위치로 고르기"""
    for key in ('type', 'loc'):
        for r in config.EVENT_VIDEOS:
            if any(w in inc[key] for w in r['match']):
                return r
    return config.DEFAULT_VIDEO


def video(src, pending, extra_cls=''):
    """영상 요소. 녹화(file)는 바로 재생, 실시간(url)은 pending에 넣었다가 flush()로 연결"""
    if src.get('file'):
        ui.element('video').props(f'src=/assets/videos/{src["file"]} muted autoplay loop playsinline') \
            .classes('cc-video local ' + extra_cls)
    else:
        v = ui.element('video').props('muted autoplay playsinline').classes('cc-video ' + extra_cls)
        pending.append((v.id, src['url']))


def flush(pending):
    for vid, url in pending:
        ui.run_javascript(f'window.sgPlay({vid}, {json.dumps(url)})')
    pending.clear()


def live_tile(src, pending):
    """ITS 실시간 영상 칸"""
    with ui.element('div').classes('cc-tile'):
        video(src, pending)
        ui.element('div').classes('cc-vignette')
        ui.label('신호 없음 · 다음 순환 때 다른 CCTV로 전환').classes('cc-nosig')
        with ui.element('div').classes('cc-top'):
            ui.label(src['name']).classes('cc-name')
            ui.space()
            with ui.element('div').classes('cc-badge cc-live'):
                ui.element('div').classes('cc-dot')
                ui.label('LIVE')
        with ui.element('div').classes('cc-bottom'):
            ui.label(src['sub'])
            ui.label().classes('cc-clock')


def offline_tile(no):
    """ITS 연결 전·키 없음: 안내 화면 (녹화 영상은 쓰지 않음)"""
    img = config.OFFLINE_IMAGE if (IMAGE_DIR / config.OFFLINE_IMAGE).exists() else None
    reason = its.data['error'] or '연결 중'
    with ui.element('div').classes('cc-tile'):
        box = ui.element('div').classes('cc-offline' + (' img' if img else ''))
        if img:
            box.style(f"background-image:url('/assets/images/{img}')")
        with box:
            ui.icon('videocam_off').style('font-size:64px')
            ui.label('실시간 CCTV 연결 대기')
            ui.label(reason).style('font-size:20px')
        with ui.element('div').classes('cc-top'):
            ui.label(f'CH{no:02d}').classes('cc-name')
            ui.space()
            ui.label('대기').classes('cc-badge cc-wait')
        with ui.element('div').classes('cc-bottom'):
            ui.label('국가교통정보센터 공개 CCTV')
            ui.label().classes('cc-clock')


def grid(n, page, pending, part=None):
    """n분할 화면의 page번째 묶음 (ITS 실시간만). 전체 페이지 수를 돌려줌"""
    ui.run_javascript('window.sgStopAll && window.sgStopAll()')
    src = sources(part)
    pages = max(1, math.ceil(len(src) / n))
    page %= pages
    chunk = src[page * n:(page + 1) * n]
    cols = 2 if n <= 4 else 3
    with ui.element('div').classes('cc-grid') \
            .style(f'grid-template-columns:repeat({cols},1fr);grid-template-rows:repeat(2,1fr)'):
        if not src:
            for i in range(n):
                offline_tile(i + 1)
        else:
            for s in chunk:
                live_tile(s, pending)
            for _ in range(n - len(chunk)):
                with ui.element('div').classes('cc-tile cc-empty'):
                    ui.label('영상 없음')
    ui.label('시연용 공개 영상 · 출처: 국가교통정보센터(ITS) 공개 CCTV · 실제 공단 CCTV 아님').classes('cc-note')
    return pages