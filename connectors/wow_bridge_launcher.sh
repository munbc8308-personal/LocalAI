#!/bin/bash
# WoW 프로세스 감지 → LoreAI bridge 자동 시작/종료
# launchd com.localai.wow-bridge 에 의해 관리됨

VENV_PYTHON="$HOME/IdeaProjects/LocalAI/.venv/bin/python"
BRIDGE_SCRIPT="$HOME/IdeaProjects/LocalAI/connectors/wow_bridge.py"
WOW_EXEC="/Applications/World of Warcraft/_retail_/World of Warcraft.app/Contents/MacOS/World of Warcraft"
WOW_LOG="/Applications/World of Warcraft/_retail_/Logs/WoWChatLog.txt"
BRIDGE_PID=""
CHATLOG_WARNED=0

log() { echo "[$(date '+%H:%M:%S')] $*"; }

wow_running() {
    # 실행파일 경로로 직접 비교 (pgrep -f 패턴보다 확실)
    pgrep -f "MacOS/World of Warcraft" > /dev/null 2>&1
}

cleanup() {
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
    log "launcher 종료"
    exit 0
}
trap cleanup SIGTERM SIGINT

log "WoW LoreAI Launcher 시작 — WoW 감지 대기 중"

while true; do
    if wow_running; then
        # chatLog 미활성화 경고 (최초 1회)
        if [ ! -f "$WOW_LOG" ] && [ "$CHATLOG_WARNED" -eq 0 ]; then
            log "경고: WoWChatLog.txt 없음 — WoW에서 /console chatLog 1 실행 필요"
            CHATLOG_WARNED=1
        fi

        if [ -z "$BRIDGE_PID" ] || ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
            log "WoW 실행 감지 — bridge 시작"
            "$VENV_PYTHON" "$BRIDGE_SCRIPT" &
            BRIDGE_PID=$!
            log "bridge PID: $BRIDGE_PID"
        fi
    else
        CHATLOG_WARNED=0
        if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
            log "WoW 종료 감지 — bridge 중단"
            kill "$BRIDGE_PID" 2>/dev/null
            wait "$BRIDGE_PID" 2>/dev/null
            BRIDGE_PID=""
        fi
    fi

    sleep 5
done
