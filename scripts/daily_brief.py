#!/usr/bin/env python3
"""매일 아침 미국 주식 시장 브리핑을 Telegram으로 전송."""

import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

LOCALAI_URL = "http://localhost:8000"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = "8131970332"
INFERENCE_TIMEOUT = 300  # 모델 추론 최대 5분

PROMPT = """어제 미국 주식 시장 브리핑을 한국어로 정리해줘.

아래 항목을 포함해서 보기 좋게 작성해줘:
1. 주요 지수 마감 현황 (S&P 500, NASDAQ, DOW Jones) — 등락률 포함
2. 주목할 종목 (상승/하락 상위 3~5개, 이유 포함)
3. 주요 뉴스·이슈 (경제지표, 기업 실적, 연준 발언 등)
4. 오늘 주목할 이벤트 (실적 발표 일정, 주요 경제지표 발표 등)"""


def query_localai(prompt: str) -> str:
    with httpx.Client(timeout=INFERENCE_TIMEOUT) as client:
        resp = client.post(
            f"{LOCALAI_URL}/v1/chat/completions",
            json={
                "model": "localai",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # 4000자 단위로 분할 (Telegram 한도 4096)
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    with httpx.Client(timeout=30) as client:
        for chunk in chunks:
            resp = client.post(url, json={"chat_id": CHAT_ID, "text": chunk})
            resp.raise_for_status()


def main() -> None:
    now = datetime.now()
    print(f"[{now:%Y-%m-%d %H:%M}] 미국 주식 브리핑 생성 시작")

    # LocalAI 서버 상태 확인
    try:
        with httpx.Client(timeout=10) as client:
            health = client.get(f"{LOCALAI_URL}/health").json()
        if not health.get("models_ready"):
            raise RuntimeError(f"모델 미준비: {health}")
    except Exception as e:
        print(f"[ERROR] LocalAI 서버 미응답: {e}", file=sys.stderr)
        sys.exit(1)

    # 브리핑 생성
    try:
        body = query_localai(PROMPT)
    except Exception as e:
        print(f"[ERROR] 브리핑 생성 실패: {e}", file=sys.stderr)
        sys.exit(1)

    message = f"📈 미국 주식 브리핑 — {now:%Y년 %m월 %d일}\n\n{body}"

    # Telegram 전송
    try:
        send_telegram(message)
        print(f"[{now:%Y-%m-%d %H:%M}] 브리핑 전송 완료")
    except Exception as e:
        print(f"[ERROR] Telegram 전송 실패: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
