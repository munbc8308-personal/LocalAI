#!/usr/bin/env python3
"""
WoW LoreAI Bridge
WoW 채팅 로그 감시 → LocalAI API → macOS TTS

실행: python -m connectors.wow_bridge
     또는: python connectors/wow_bridge.py
"""

import re
import subprocess
import threading
import time
from pathlib import Path

import httpx

# ── 설정 ──────────────────────────────────────────────────────────────────────

WOW_LOG = Path("/Applications/World of Warcraft/_retail_/Logs/WoWChatLog.txt")
LOCALAI_URL = "http://localhost:8000/v1/chat/completions"
SESSION_ID = "wow-loreai"

ZONE_SYSTEM = (
    "당신은 World of Warcraft의 현명한 로어마스터입니다. "
    "플레이어가 새 지역에 입장하면 그 지역의 역사·전설·흥미로운 사실을 소개합니다.\n"
    "규칙:\n"
    "- 2~3문장으로 간결하게\n"
    "- 세계관 내 화자 시점으로 ('이 땅은...', '전설에 의하면...')\n"
    "- 한국어, 웅장하고 신비로운 톤"
)

ASK_SYSTEM = (
    "당신은 World of Warcraft 전문가입니다. "
    "플레이어의 WoW 관련 질문에 2~4문장으로 간결하게 한국어로 답합니다."
)

# ── TTS ───────────────────────────────────────────────────────────────────────

def _find_korean_voice() -> str:
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
    # 선호 순서
    for name in ("Yuna", "Reed", "Eddy", "Flo"):
        if name in result.stdout:
            return name
    for line in result.stdout.splitlines():
        if "ko_" in line or "(ko_" in line:
            return line.split()[0]
    return ""

_TTS_VOICE = _find_korean_voice()
_tts_lock = threading.Lock()


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

# ── 로그 파서 ─────────────────────────────────────────────────────────────────

# 예시 로그 라인:
# 12/1 14:23:45.678  CHAT_MSG_WHISPER_INFORM,...,"[LoreAI]zone:Stormwind City",...
_PATTERN = re.compile(r'\[LoreAI\](zone|ask):([^"\n]+)')


def _parse_line(line: str) -> tuple[str, str] | None:
    m = _PATTERN.search(line)
    if not m:
        return None
    kind    = m.group(1)
    content = m.group(2).strip().rstrip('",')
    return kind, content

# ── 파일 워처 ─────────────────────────────────────────────────────────────────

def _tail(path: Path):
    while not path.exists():
        print(f"[bridge] 로그 파일 없음, 대기 중: {path}")
        print("[bridge]  → WoW에서 /console chatLog 1 실행 후 재로그인 필요")
        time.sleep(5)

    with open(path, encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)
        print(f"[bridge] 감시 시작: {path}")
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.2)
                continue
            yield line

# ── 핸들러 ────────────────────────────────────────────────────────────────────

def _handle_zone(zone: str) -> None:
    response = ask_localai(ZONE_SYSTEM, f"플레이어가 '{zone}'에 입장했습니다. 이 지역을 소개해주세요.")
    if response:
        print(f"[bridge] 로어: {response[:100]}...")
        speak(response)


def _handle_ask(question: str) -> None:
    response = ask_localai(ASK_SYSTEM, question)
    if response:
        print(f"[bridge] 답변: {response[:100]}...")
        speak(response)

# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[bridge] TTS 음성: {_TTS_VOICE or '시스템 기본'}")
    print(f"[bridge] LocalAI:  {LOCALAI_URL}")

    try:
        httpx.get("http://localhost:8000/health", timeout=5).raise_for_status()
        print("[bridge] LocalAI 연결 OK")
    except Exception as e:
        print(f"[bridge] 경고: LocalAI 응답 없음 — {e}")

    for line in _tail(WOW_LOG):
        if "[LoreAI]" not in line:
            continue

        parsed = _parse_line(line)
        if not parsed:
            continue

        kind, content = parsed
        print(f"[bridge] [{kind}] {content}")

        if kind == "zone":
            threading.Thread(target=_handle_zone, args=(content,), daemon=True).start()
        elif kind == "ask":
            threading.Thread(target=_handle_ask, args=(content,), daemon=True).start()


if __name__ == "__main__":
    main()
