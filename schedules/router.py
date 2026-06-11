from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db, sync_job
from .runner import execute

router = APIRouter()


# ── Pydantic 스키마 ────────────────────────────────────────────────────────────

class ScheduleBody(BaseModel):
    name: str
    topic: str
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)
    chat_id: str
    active: bool = True


class ScheduleResponse(BaseModel):
    id: int
    name: str
    topic: str
    hour: int
    minute: int
    chat_id: str
    active: bool
    created_at: str
    last_run_at: str | None
    last_status: str | None

    @classmethod
    def from_db(cls, s: db.Schedule) -> "ScheduleResponse":
        return cls(**{k: v for k, v in s.__dict__.items() if k != "id"}, id=s.id)


# ── API ───────────────────────────────────────────────────────────────────────

@router.get("/v1/schedules", response_model=list[ScheduleResponse])
def list_schedules():
    return [ScheduleResponse.from_db(s) for s in db.list_schedules()]


@router.post("/v1/schedules", response_model=ScheduleResponse, status_code=201)
def create_schedule(body: ScheduleBody):
    s = db.Schedule(**body.model_dump())
    created = db.create_schedule(s)
    sync_job(created.id)
    return ScheduleResponse.from_db(created)


@router.put("/v1/schedules/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(schedule_id: int, body: ScheduleBody):
    s = db.get_schedule(schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="스케줄 없음")
    s.name = body.name
    s.topic = body.topic
    s.hour = body.hour
    s.minute = body.minute
    s.chat_id = body.chat_id
    s.active = body.active
    db.update_schedule(s)
    sync_job(schedule_id)
    return ScheduleResponse.from_db(db.get_schedule(schedule_id))


@router.delete("/v1/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int):
    if not db.get_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="스케줄 없음")
    db.delete_schedule(schedule_id)
    sync_job(schedule_id)


@router.patch("/v1/schedules/{schedule_id}/toggle", response_model=ScheduleResponse)
def toggle_schedule(schedule_id: int):
    if not db.get_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="스케줄 없음")
    db.toggle_active(schedule_id)
    sync_job(schedule_id)
    return ScheduleResponse.from_db(db.get_schedule(schedule_id))


@router.post("/v1/schedules/{schedule_id}/run")
async def run_now(schedule_id: int, background_tasks: BackgroundTasks):
    if not db.get_schedule(schedule_id):
        raise HTTPException(status_code=404, detail="스케줄 없음")
    background_tasks.add_task(execute, schedule_id)
    return {"message": "실행 시작됨"}


# ── Web UI ────────────────────────────────────────────────────────────────────

@router.get("/schedules", response_class=HTMLResponse)
def schedules_ui():
    return HTMLResponse(_HTML)


_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LocalAI — 스케줄 관리</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f172a; --surface: #1e293b; --border: #334155;
    --text: #f1f5f9; --muted: #94a3b8; --primary: #3b82f6;
    --primary-hover: #2563eb; --success: #22c55e; --danger: #ef4444;
    --warning: #f59e0b; --radius: 12px;
  }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-height: 100vh; }
  header { display: flex; align-items: center; justify-content: space-between; padding: 24px 32px; border-bottom: 1px solid var(--border); }
  header h1 { font-size: 20px; font-weight: 700; }
  header span { color: var(--muted); font-size: 14px; margin-left: 10px; font-weight: 400; }
  main { max-width: 860px; margin: 0 auto; padding: 32px 16px; }
  .empty { text-align: center; padding: 80px 0; color: var(--muted); }
  .empty p { margin-top: 8px; font-size: 14px; }

  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 24px; margin-bottom: 12px; display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; }
  .card-left {}
  .card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
  .card-name { font-weight: 600; font-size: 16px; }
  .badge-time { background: var(--primary); color: #fff; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 20px; white-space: nowrap; }
  .badge-off { background: var(--border); color: var(--muted); }
  .card-topic { color: var(--muted); font-size: 14px; line-height: 1.5; max-height: 44px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin-bottom: 10px; }
  .card-meta { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 8px; }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
  .status-success { background: var(--success); }
  .status-fail { background: var(--danger); }
  .status-none { background: var(--border); }

  /* Actions */
  .card-actions { display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
  .toggle { position: relative; width: 44px; height: 24px; cursor: pointer; margin-bottom: 4px; }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; inset: 0; background: var(--border); border-radius: 24px; transition: .2s; }
  .slider::before { content: ''; position: absolute; width: 18px; height: 18px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: .2s; }
  input:checked + .slider { background: var(--success); }
  input:checked + .slider::before { transform: translateX(20px); }

  .btn-group { display: flex; gap: 6px; }
  button { cursor: pointer; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; padding: 6px 12px; transition: opacity .15s; }
  button:hover { opacity: .85; }
  button:active { opacity: .7; }
  .btn-run { background: var(--primary); color: #fff; }
  .btn-edit { background: var(--border); color: var(--text); }
  .btn-del { background: transparent; color: var(--danger); border: 1px solid var(--danger); }
  .btn-add { background: var(--primary); color: #fff; padding: 8px 18px; font-size: 14px; border-radius: 8px; }

  /* Modal */
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 16px; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); width: 100%; max-width: 520px; padding: 28px; }
  .modal h2 { font-size: 17px; font-weight: 700; margin-bottom: 20px; }
  .form-group { margin-bottom: 16px; }
  label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
  input[type=text], input[type=number], textarea, select {
    width: 100%; background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    color: var(--text); padding: 9px 12px; font-size: 14px; outline: none;
    transition: border-color .15s;
  }
  input:focus, textarea:focus { border-color: var(--primary); }
  textarea { resize: vertical; min-height: 110px; font-family: inherit; line-height: 1.5; }
  .time-row { display: flex; gap: 10px; }
  .time-row input { flex: 1; }
  .form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 22px; }
  .btn-cancel { background: var(--border); color: var(--text); padding: 8px 18px; }
  .btn-save { background: var(--primary); color: #fff; padding: 8px 18px; }
  .btn-save:disabled { opacity: .5; cursor: default; }
  .hidden { display: none !important; }

  /* Toast */
  #toast { position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%); background: #1e293b; border: 1px solid var(--border); color: var(--text); padding: 10px 20px; border-radius: 8px; font-size: 14px; z-index: 200; transition: opacity .3s; pointer-events: none; }
  #toast.show { opacity: 1; } #toast.hide { opacity: 0; }

  /* Spinner */
  .spinner { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; display: inline-block; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<header>
  <div><h1>📋 브리핑 스케줄<span>LocalAI</span></h1></div>
  <button class="btn-add" onclick="openModal()">+ 새 스케줄</button>
</header>
<main>
  <div id="list"></div>
</main>

<!-- Modal -->
<div id="overlay" class="overlay hidden" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <h2 id="modal-title">새 스케줄</h2>
    <div class="form-group">
      <label>이름</label>
      <input id="f-name" type="text" placeholder="미국 주식 브리핑" maxlength="60">
    </div>
    <div class="form-group">
      <label>조사할 내용 (프롬프트)</label>
      <textarea id="f-topic" placeholder="어제 미국 주식 시장 브리핑을 한국어로 정리해줘. 주요 지수 등락률, 주목 종목, 주요 뉴스, 오늘 이벤트 포함."></textarea>
    </div>
    <div class="form-group">
      <label>전송 시각</label>
      <div class="time-row">
        <input id="f-hour" type="number" min="0" max="23" placeholder="시 (0~23)">
        <input id="f-minute" type="number" min="0" max="59" placeholder="분 (0~59)">
      </div>
    </div>
    <div class="form-group">
      <label>Telegram Chat ID</label>
      <input id="f-chatid" type="text" placeholder="8131970332">
    </div>
    <div class="form-actions">
      <button class="btn-cancel" onclick="closeModal()">취소</button>
      <button class="btn-save" id="btn-save" onclick="saveSchedule()">저장</button>
    </div>
  </div>
</div>

<div id="toast" class="hide"></div>

<script>
let editingId = null;

async function loadSchedules() {
  const res = await fetch('/v1/schedules');
  const list = await res.json();
  const el = document.getElementById('list');
  if (!list.length) {
    el.innerHTML = '<div class="empty"><div style="font-size:40px">🗓️</div><p>등록된 스케줄이 없습니다.<br>오른쪽 위 버튼으로 추가하세요.</p></div>';
    return;
  }
  el.innerHTML = list.map(renderCard).join('');
}

function renderCard(s) {
  const timeLabel = `${String(s.hour).padStart(2,'0')}:${String(s.minute).padStart(2,'0')}`;
  const badgeClass = s.active ? 'badge-time' : 'badge-time badge-off';
  const statusDot = !s.last_status ? 'status-none' : s.last_status === '성공' ? 'status-success' : 'status-fail';
  const metaText = s.last_run_at
    ? `마지막 실행: ${s.last_run_at} — ${s.last_status}`
    : '아직 실행되지 않음';
  return `
  <div class="card" id="card-${s.id}">
    <div class="card-left">
      <div class="card-header">
        <span class="card-name">${esc(s.name)}</span>
        <span class="${badgeClass}">매일 ${timeLabel}</span>
      </div>
      <div class="card-topic">${esc(s.topic)}</div>
      <div class="card-meta">
        <span class="status-dot ${statusDot}"></span>
        ${esc(metaText)}
      </div>
    </div>
    <div class="card-actions">
      <label class="toggle" title="${s.active ? '비활성화' : '활성화'}">
        <input type="checkbox" ${s.active ? 'checked' : ''} onchange="toggleSchedule(${s.id}, this)">
        <span class="slider"></span>
      </label>
      <div class="btn-group">
        <button class="btn-run" id="run-${s.id}" onclick="runNow(${s.id})">지금 실행</button>
        <button class="btn-edit" onclick="openModal(${s.id})">수정</button>
        <button class="btn-del" onclick="deleteSchedule(${s.id})">삭제</button>
      </div>
    </div>
  </div>`;
}

function openModal(id = null) {
  editingId = id;
  document.getElementById('modal-title').textContent = id ? '스케줄 수정' : '새 스케줄';
  if (id) {
    fetch(`/v1/schedules`).then(r => r.json()).then(list => {
      const s = list.find(x => x.id === id);
      if (!s) return;
      document.getElementById('f-name').value = s.name;
      document.getElementById('f-topic').value = s.topic;
      document.getElementById('f-hour').value = s.hour;
      document.getElementById('f-minute').value = s.minute;
      document.getElementById('f-chatid').value = s.chat_id;
    });
  } else {
    document.getElementById('f-name').value = '';
    document.getElementById('f-topic').value = '';
    document.getElementById('f-hour').value = '';
    document.getElementById('f-minute').value = '';
    document.getElementById('f-chatid').value = '8131970332';
  }
  document.getElementById('overlay').classList.remove('hidden');
  document.getElementById('f-name').focus();
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('overlay')) return;
  document.getElementById('overlay').classList.add('hidden');
  editingId = null;
}

async function saveSchedule() {
  const name = document.getElementById('f-name').value.trim();
  const topic = document.getElementById('f-topic').value.trim();
  const hour = parseInt(document.getElementById('f-hour').value);
  const minute = parseInt(document.getElementById('f-minute').value);
  const chat_id = document.getElementById('f-chatid').value.trim();

  if (!name || !topic || isNaN(hour) || isNaN(minute) || !chat_id) {
    toast('모든 항목을 입력하세요', 'warn'); return;
  }
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    toast('시/분 값을 확인하세요', 'warn'); return;
  }

  const btn = document.getElementById('btn-save');
  btn.disabled = true; btn.textContent = '저장 중...';

  const body = { name, topic, hour, minute, chat_id, active: true };
  const url = editingId ? `/v1/schedules/${editingId}` : '/v1/schedules';
  const method = editingId ? 'PUT' : 'POST';

  try {
    const res = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (!res.ok) throw new Error(await res.text());
    document.getElementById('overlay').classList.add('hidden');
    editingId = null;
    await loadSchedules();
    toast(method === 'POST' ? '스케줄 추가됨' : '스케줄 수정됨');
  } catch(e) {
    toast('저장 실패: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '저장';
  }
}

async function deleteSchedule(id) {
  if (!confirm('스케줄을 삭제할까요?')) return;
  await fetch(`/v1/schedules/${id}`, { method: 'DELETE' });
  await loadSchedules();
  toast('삭제됨');
}

async function toggleSchedule(id, checkbox) {
  const res = await fetch(`/v1/schedules/${id}/toggle`, { method: 'PATCH' });
  const s = await res.json();
  toast(s.active ? '활성화됨' : '비활성화됨');
  await loadSchedules();
}

async function runNow(id) {
  const btn = document.getElementById(`run-${id}`);
  btn.innerHTML = '<span class="spinner"></span>';
  btn.disabled = true;
  try {
    await fetch(`/v1/schedules/${id}/run`, { method: 'POST' });
    toast('실행 시작됨 — 완료까지 수분 소요');
    // 10초 후 상태 갱신
    setTimeout(loadSchedules, 10000);
    setTimeout(loadSchedules, 60000);
    setTimeout(loadSchedules, 180000);
  } catch(e) {
    toast('실행 실패', 'error');
  } finally {
    btn.innerHTML = '지금 실행';
    btn.disabled = false;
  }
}

function toast(msg, type = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = type === 'error' ? '#ef4444' : type === 'warn' ? '#f59e0b' : '#334155';
  el.className = 'show';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = 'hide'; }, 2800);
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Keyboard shortcut: Escape to close modal
document.addEventListener('keydown', e => { if (e.key === 'Escape') { document.getElementById('overlay').classList.add('hidden'); editingId = null; } });

loadSchedules();
</script>
</body>
</html>
"""
