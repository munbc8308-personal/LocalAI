import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from . import db

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

LOCALAI_URL = "http://localhost:8000"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
INFERENCE_TIMEOUT = 1200  # 20분 — 27B 오케스트레이터 + 검색 + 합성 + 판정 여유


async def execute(schedule_id: int) -> str:
    """스케줄을 실행하고 상태 문자열을 반환."""
    schedule = db.get_schedule(schedule_id)
    if not schedule:
        return "스케줄 없음"

    if not TELEGRAM_TOKEN:
        db.update_run_status(schedule_id, "실패: TELEGRAM_BOT_TOKEN 미설정")
        return "실패: TELEGRAM_BOT_TOKEN 미설정"

    try:
        body = await _query_localai(schedule.topic)
        await _send_telegram(schedule.chat_id, schedule.name, body)
        status = "성공"
        logger.info(f"[schedules] id={schedule_id} '{schedule.name}' 전송 완료")
    except Exception as e:
        status = f"실패: {type(e).__name__}: {e}"
        logger.error(f"[schedules] id={schedule_id} '{schedule.name}' 오류: {type(e).__name__}: {e}", exc_info=True)

    db.update_run_status(schedule_id, status)
    return status


async def _query_localai(topic: str) -> str:
    async with httpx.AsyncClient(timeout=INFERENCE_TIMEOUT) as client:
        resp = await client.post(
            f"{LOCALAI_URL}/v1/chat/completions",
            json={
                "model": "localai",
                "messages": [{"role": "user", "content": topic}],
                "stream": False,
                "max_iterations": 1,  # 스케줄 작업은 judge 재시도 없이 1회만 — 시간 절약
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _send_telegram(chat_id: str, name: str, body: str) -> None:
    from datetime import datetime

    header = f"📋 {name}\n{datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}\n{'─' * 30}\n\n"
    full_text = header + body
    chunks = [full_text[i : i + 4000] for i in range(0, len(full_text), 4000)]

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        for chunk in chunks:
            resp = await client.post(url, json={"chat_id": chat_id, "text": chunk})
            resp.raise_for_status()
