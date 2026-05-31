#!/bin/bash
# LocalAI launchd 서비스 관리 스크립트
# 사용법: ./scripts/service.sh [install|uninstall|start|stop|restart|status|logs]

PLIST_NAME="com.localai.server"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

case "$1" in
  install)
    echo "launchd 서비스 등록..."
    cp "$(dirname "$0")/../launchd/$PLIST_NAME.plist" "$PLIST_PATH"
    launchctl load "$PLIST_PATH"
    echo "완료. 'service.sh status' 로 확인하세요."
    ;;
  uninstall)
    echo "launchd 서비스 제거..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "완료."
    ;;
  start)
    launchctl start "$PLIST_NAME"
    echo "서비스 시작됨"
    ;;
  stop)
    launchctl stop "$PLIST_NAME"
    echo "서비스 중지됨"
    ;;
  restart)
    launchctl stop "$PLIST_NAME"
    sleep 2
    launchctl start "$PLIST_NAME"
    echo "서비스 재시작됨"
    ;;
  status)
    echo "=== launchd 상태 ==="
    launchctl list | grep localai || echo "등록되지 않음"
    echo ""
    echo "=== 서버 헬스 ==="
    curl -s http://localhost:8000/health 2>/dev/null | python3 -m json.tool || echo "서버 미응답"
    ;;
  logs)
    tail -f /tmp/localai.stdout.log
    ;;
  *)
    echo "사용법: $0 {install|uninstall|start|stop|restart|status|logs}"
    exit 1
    ;;
esac
