from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def chat_ui():
    return HTMLResponse(_HTML)


_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LocalAI</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0f0f0f;
    --surface: #1a1a1a;
    --border: #2a2a2a;
    --text: #e8e8e8;
    --text-muted: #888;
    --accent: #7c6af7;
    --accent-hover: #9b8fff;
    --user-bg: #1e1b3a;
    --ai-bg: #1a1a1a;
    --input-bg: #141414;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Header */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    flex-shrink: 0;
  }
  header h1 {
    font-size: 16px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.5px;
  }
  #session-badge {
    font-size: 11px;
    color: var(--text-muted);
    background: var(--border);
    padding: 3px 8px;
    border-radius: 10px;
  }
  #clear-btn {
    font-size: 12px;
    color: var(--text-muted);
    background: none;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    transition: all 0.15s;
  }
  #clear-btn:hover { color: var(--text); border-color: var(--text-muted); }

  /* Messages */
  #messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px 0;
    scroll-behavior: smooth;
  }
  #messages::-webkit-scrollbar { width: 4px; }
  #messages::-webkit-scrollbar-track { background: transparent; }
  #messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .msg {
    display: flex;
    gap: 12px;
    padding: 10px 20px;
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

  .msg-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .msg.user .msg-avatar { background: var(--accent); color: #fff; }
  .msg.ai   .msg-avatar { background: var(--border); color: var(--text-muted); }

  .msg-body { flex: 1; min-width: 0; }
  .msg-role { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; font-weight: 500; }

  .msg-content {
    font-size: 14px;
    line-height: 1.65;
    color: var(--text);
    word-break: break-word;
  }
  /* Markdown */
  .msg-content p { margin-bottom: 10px; }
  .msg-content p:last-child { margin-bottom: 0; }
  .msg-content h1,.msg-content h2,.msg-content h3 { margin: 14px 0 6px; font-weight: 600; }
  .msg-content h1 { font-size: 18px; }
  .msg-content h2 { font-size: 16px; }
  .msg-content h3 { font-size: 14px; }
  .msg-content ul,.msg-content ol { padding-left: 20px; margin-bottom: 10px; }
  .msg-content li { margin-bottom: 3px; }
  .msg-content code {
    background: #2a2a2a;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
  }
  .msg-content pre {
    background: #0d0d0d;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
    overflow-x: auto;
    margin: 10px 0;
  }
  .msg-content pre code {
    background: none;
    padding: 0;
    font-size: 13px;
  }
  .msg-content blockquote {
    border-left: 3px solid var(--accent);
    padding-left: 12px;
    color: var(--text-muted);
    margin: 8px 0;
  }
  .msg-content table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }
  .msg-content th,.msg-content td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
  .msg-content th { background: var(--surface); }
  .msg-content a { color: var(--accent-hover); text-decoration: none; }
  .msg-content a:hover { text-decoration: underline; }

  /* Thinking cursor */
  .cursor::after {
    content: '▋';
    animation: blink 0.8s step-end infinite;
    color: var(--accent);
  }
  @keyframes blink { 50% { opacity: 0; } }

  /* Empty state */
  #empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    gap: 8px;
    user-select: none;
  }
  #empty .logo { font-size: 36px; margin-bottom: 8px; }
  #empty h2 { font-size: 18px; color: var(--text); font-weight: 500; }
  #empty p { font-size: 13px; }

  /* Input area */
  #input-area {
    border-top: 1px solid var(--border);
    padding: 12px 20px 16px;
    background: var(--surface);
    flex-shrink: 0;
  }
  #input-wrap {
    max-width: 900px;
    margin: 0 auto;
    display: flex;
    gap: 10px;
    align-items: flex-end;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 8px 10px 8px 14px;
    transition: border-color 0.15s;
  }
  #input-wrap:focus-within { border-color: var(--accent); }
  #input {
    flex: 1;
    background: none;
    border: none;
    outline: none;
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    resize: none;
    max-height: 160px;
    min-height: 24px;
    font-family: inherit;
  }
  #input::placeholder { color: var(--text-muted); }
  #send-btn {
    background: var(--accent);
    border: none;
    border-radius: 8px;
    width: 34px;
    height: 34px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.15s, opacity 0.15s;
    color: white;
  }
  #send-btn:hover { background: var(--accent-hover); }
  #send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  #send-btn svg { width: 16px; height: 16px; }
  #hint { font-size: 11px; color: var(--text-muted); text-align: center; margin-top: 8px; max-width: 900px; margin-left: auto; margin-right: auto; }
</style>
</head>
<body>

<header>
  <h1>⚡ LocalAI</h1>
  <div style="display:flex;gap:8px;align-items:center">
    <span id="session-badge">session: web</span>
    <button id="clear-btn" onclick="clearSession()">초기화</button>
  </div>
</header>

<div id="messages">
  <div id="empty">
    <div class="logo">🤖</div>
    <h2>LocalAI에 오신 걸 환영합니다</h2>
    <p>질문을 입력하면 답변합니다</p>
  </div>
</div>

<div id="input-area">
  <div id="input-wrap">
    <textarea id="input" rows="1" placeholder="메시지를 입력하세요... (Shift+Enter 줄바꿈)" maxlength="8000"></textarea>
    <button id="send-btn" onclick="sendMessage()" title="전송 (Enter)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
      </svg>
    </button>
  </div>
  <div id="hint">Enter 전송 · Shift+Enter 줄바꿈</div>
</div>

<script>
const SESSION_ID = 'web-' + Math.random().toString(36).slice(2, 8);
document.getElementById('session-badge').textContent = 'session: ' + SESSION_ID;

marked.setOptions({ breaks: true, gfm: true });

const messagesEl = document.getElementById('messages');
const inputEl    = document.getElementById('input');
const sendBtn    = document.getElementById('send-btn');
const emptyEl    = document.getElementById('empty');
let isStreaming  = false;

// Auto-resize textarea
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + 'px';
});

inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isStreaming) sendMessage();
  }
});

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, content, streaming = false) {
  if (emptyEl) emptyEl.style.display = 'none';
  const div = document.createElement('div');
  div.className = 'msg ' + (role === 'user' ? 'user' : 'ai');

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '나' : 'AI';

  const body = document.createElement('div');
  body.className = 'msg-body';

  const roleEl = document.createElement('div');
  roleEl.className = 'msg-role';
  roleEl.textContent = role === 'user' ? '나' : 'LocalAI';

  const contentEl = document.createElement('div');
  contentEl.className = 'msg-content' + (streaming ? ' cursor' : '');

  if (role === 'user') {
    contentEl.textContent = content;
  } else {
    contentEl.innerHTML = marked.parse(content || '');
    contentEl.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
  }

  body.appendChild(roleEl);
  body.appendChild(contentEl);
  div.appendChild(avatar);
  div.appendChild(body);
  messagesEl.appendChild(div);
  scrollBottom();
  return contentEl;
}

function updateContent(el, text, done = false) {
  el.innerHTML = marked.parse(text);
  el.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b));
  if (done) {
    el.classList.remove('cursor');
  } else {
    el.classList.add('cursor');
  }
  scrollBottom();
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || isStreaming) return;

  addMessage('user', text);
  inputEl.value = '';
  inputEl.style.height = 'auto';
  inputEl.focus();

  isStreaming = true;
  sendBtn.disabled = true;

  const aiEl = addMessage('ai', '', true);
  let accumulated = '';

  try {
    const resp = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Id': SESSION_ID,
      },
      body: JSON.stringify({
        model: 'localai',
        messages: [{ role: 'user', content: text }],
        stream: true,
      }),
    });

    if (!resp.ok) throw new Error('HTTP ' + resp.status);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const lines = decoder.decode(value, { stream: true }).split('\\n');
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') break;
        try {
          const chunk = JSON.parse(data);
          const content = chunk?.choices?.[0]?.delta?.content;
          if (content) {
            accumulated += content;
            updateContent(aiEl, accumulated, false);
          }
        } catch {}
      }
    }
    updateContent(aiEl, accumulated, true);
  } catch (err) {
    updateContent(aiEl, '오류가 발생했습니다: ' + err.message, true);
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

async function clearSession() {
  try {
    await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': SESSION_ID },
      body: JSON.stringify({ model: 'localai', messages: [{ role: 'user', content: '/clear' }], stream: false }),
    });
  } catch {}
  messagesEl.innerHTML = '';
  messagesEl.appendChild(emptyEl);
  emptyEl.style.display = 'flex';
}

inputEl.focus();
</script>
</body>
</html>"""
