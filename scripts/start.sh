#!/bin/bash
# LocalAI 서버 시작 스크립트 (launchd에서 호출)

set -e

PROJECT_DIR="/Users/munbyeongcheon/IdeaProjects/LocalAI"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
UVICORN="$PROJECT_DIR/.venv/bin/uvicorn"

cd "$PROJECT_DIR"

# SearXNG Docker 컨테이너 확인 및 시작
if command -v docker &>/dev/null; then
    if ! docker ps --filter "name=localai-searxng" --filter "status=running" | grep -q localai-searxng; then
        echo "[start.sh] SearXNG 컨테이너 시작..."
        docker compose -f "$PROJECT_DIR/docker/docker-compose.yml" up -d
        sleep 3
    else
        echo "[start.sh] SearXNG 이미 실행 중"
    fi
fi

echo "[start.sh] LocalAI 서버 시작..."
exec "$UVICORN" api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info
