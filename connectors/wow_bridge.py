#!/usr/bin/env python3
"""
WoW LoreAI Bridge
SavedVariables(LoreAI.lua) 감시 → LocalAI API → macOS TTS

ReloadUI가 발생할 때 WoW가 LoreAI.lua를 디스크에 씀.
Python이 파일 변경을 감지하고 request 필드를 읽어 처리.
"""

import re
import subprocess
import threading
import time
from pathlib import Path

import httpx

# ── 설정 ──────────────────────────────────────────────────────────────────────

# WoW 계정 ID — WTF 폴더에서 자동 탐색
WTF_BASE = Path("/Applications/World of Warcraft/_retail_/WTF/Account")
LOCALAI_URL = "http://localhost:8000/v1/chat/completions"
SESSION_ID = "wow-loreai"

ASK_SYSTEM = (
    "당신은 World of Warcraft 전문가입니다. "
    "플레이어의 WoW 관련 질문에 2~4문장으로 간결하게 한국어로 답합니다."
)

ZONE_SYSTEM = (
    "당신은 World of Warcraft의 현명한 로어마스터입니다. "
    "플레이어가 새 지역에 입장하면 그 지역의 역사·전설·흥미로운 사실을 소개합니다.\n"
    "규칙:\n"
    "- 2~3문장으로 간결하게\n"
    "- 세계관 내 화자 시점으로 ('이 땅은...', '전설에 의하면...')\n"
    "- 한국어, 웅장하고 신비로운 톤"
)

# ── SavedVariables 파일 탐색 ───────────────────────────────────────────────────

def find_savedvars() -> Path | None:
    """LoreAI.lua SavedVariables 파일 탐색."""
    matches = list(WTF_BASE.rglob("SavedVariables/LoreAI.lua"))
    if not matches:
        return None
    # 가장 최근 수정된 파일
    return max(matches, key=lambda p: p.stat().st_mtime)

# ── SavedVariables 파서 ────────────────────────────────────────────────────────

_REQ_PATTERN = re.compile(r'request\s*=\s*"([^"]+)"')
_TS_PATTERN  = re.compile(r'timestamp\s*=\s*(\d+)')


def parse_request(text: str) -> tuple[str, int] | None:
    """LoreAI.lua에서 request와 timestamp 추출."""
    req = _REQ_PATTERN.search(text)
    ts  = _TS_PATTERN.search(text)
    if not req:
        return None
    return req.group(1), int(ts.group(1)) if ts else 0

# ── TTS ───────────────────────────────────────────────────────────────────────

def _find_korean_voice() -> str:
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
    for name in ("Yuna", "Reed", "Eddy", "Flo"):
        if name in result.stdout:
            return name
    for line in result.stdout.splitlines():
        if "ko_" in line:
            return line.split()[0]
    return ""

_TTS_VOICE = _find_korean_voice()
_tts_lock  = threading.Lock()


def speak(text: str) -> None:
    def _run():
        with _tts_lock:
            cmd = ["say"]
            if _TTS_VOICE:
                cmd += ["-v", _TTS_VOICE]
            cmd.append(text)
            subprocess.run(cmd)
    threading.Thread(target=_run, daemon=True).start()

# ── LocalAI ───────────────────────────────────────────────────────────────────

def ask_localai(system: str, user_msg: str) -> str:
    try:
        resp = httpx.post(
            LOCALAI_URL,
            json={
                "model": "localai",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
            },
            headers={"X-Session-Id": SESSION_ID},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[bridge] LocalAI 오류: {e}")
        return ""

# ── 핸들러 ────────────────────────────────────────────────────────────────────

def _handle(kind: str, content: str) -> None:
    if kind == "zone":
        system = ZONE_SYSTEM
        prompt = f"플레이어가 '{content}'에 입장했습니다. 이 지역을 소개해주세요."
    else:
        system = ASK_SYSTEM
        prompt = content

    print(f"[bridge] [{kind}] {content}")
    response = ask_localai(system, prompt)
    if response:
        print(f"[bridge] 응답: {response[:80]}...")
        speak(response)

# ── 파일 감시 루프 ────────────────────────────────────────────────────────────

def watch_loop() -> None:
    sv_path: Path | None = None
    last_ts = 0
    last_mtime = 0.0

    print("[bridge] SavedVariables 감시 시작...")

    while True:
        # 경로 탐색 (최초 or 재로그인 후)
        if sv_path is None or not sv_path.exists():
            sv_path = find_savedvars()
            if sv_path is None:
                time.sleep(3)
                continue
            print(f"[bridge] 감시 중: {sv_path}")

        try:
            mtime = sv_path.stat().st_mtime
            if mtime == last_mtime:
                time.sleep(0.5)
                continue

            last_mtime = mtime
            text = sv_path.read_text(encoding="utf-8", errors="ignore")
            parsed = parse_request(text)
            if parsed is None:
                time.sleep(0.5)
                continue

            request, ts = parsed
            if ts <= last_ts or not request:
                time.sleep(0.5)
                continue

            last_ts = ts

            # "ask:질문" or "zone:지역명"
            if ":" in request:
                kind, content = request.split(":", 1)
                threading.Thread(target=_handle, args=(kind, content), daemon=True).start()

        except Exception as e:
            print(f"[bridge] 감시 오류: {e}")

        time.sleep(0.5)

# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[bridge] TTS 음성: {_TTS_VOICE or '시스템 기본'}")
    print(f"[bridge] LocalAI:  {LOCALAI_URL}")

    try:
        httpx.get("http://localhost:8000/health", timeout=5).raise_for_status()
        print("[bridge] LocalAI 연결 OK")
    except Exception as e:
        print(f"[bridge] 경고: LocalAI 응답 없음 — {e}")

    watch_loop()


if __name__ == "__main__":
    main()
