#!/bin/bash
# WoW 프로세스 감지 → LoreAI bridge 자동 시작/종료
# launchd com.localai.wow-bridge 에 의해 관리됨

VENV_PYTHON="$HOME/IdeaProjects/LocalAI/.venv/bin/python"
BRIDGE_SCRIPT="$HOME/IdeaProjects/LocalAI/connectors/wow_bridge.py"
BRIDGE_PID=""

log() { echo "[$(date '+%H:%M:%S')] $*"; }

cleanup() {
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
    log "launcher 종료"
    exit 0
}
trap cleanup SIGTERM SIGINT

log "WoW LoreAI Launcher 시작 — WoW 감지 대기 중"

while true; do
    # _retail_ 게임 프로세스만 매칭 (Launcher 제외)
    if pgrep -f "_retail_/World of Warcraft.app" > /dev/null 2>&1; then
        if [ -z "$BRIDGE_PID" ] || ! kill -0 "$BRIDGE_PID" 2>/dev/null; then
            log "WoW 실행 감지 — bridge 시작"
            "$VENV_PYTHON" "$BRIDGE_SCRIPT" &
            BRIDGE_PID=$!
            log "bridge PID: $BRIDGE_PID"
        fi
    else
        if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
            log "WoW 종료 감지 — bridge 중단"
            kill "$BRIDGE_PID" 2>/dev/null
            wait "$BRIDGE_PID" 2>/dev/null
            BRIDGE_PID=""
        fi
    fi

    sleep 5
done
