#!/bin/bash
# LocalAI 서비스 일일 재시작 (메모리 누수 및 ChromaDB Rust 크래시 방지)
# launchd KeepAlive가 30초 내에 자동 재시작

LOG="/Users/munbyeongcheon/IdeaProjects/LocalAI/data/restart.log"
mkdir -p "$(dirname "$LOG")"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 일일 재시작 실행" >> "$LOG"
launchctl stop com.localai.server
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 재시작 신호 전송 완료 (launchd가 재시작)" >> "$LOG"
