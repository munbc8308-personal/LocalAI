"""
금융 시장 데이터 — yfinance 기반.
실시간 주요 지수, 개별 종목, 환율, 원자재 조회.
"""
import logging
import re
from datetime import datetime

import yfinance as yf

logger = logging.getLogger(__name__)

_MARKET_TICKERS: dict[str, str] = {
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "Dow Jones": "^DJI",
    "VIX": "^VIX",
    "USD/KRW": "KRW=X",
    "EUR/KRW": "EURKRW=X",
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD",
    "WTI Oil": "CL=F",
    "Gold": "GC=F",
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
}

TOOL_NAMES = {"get_market_snapshot", "get_quote"}

_FINANCE_KEYWORDS = re.compile(
    r"S&P|나스닥|NASDAQ|다우|Dow|코스피|KOSPI|코스닥|KOSDAQ|"
    r"주가|증시|지수|환율|달러|비트코인|이더리움|유가|금값|WTI|VIX|"
    r"market|stock price|S&P 500|wall street",
    re.IGNORECASE,
)


def _fmt(val, digits: int = 2):
    try:
        return round(float(val), digits)
    except (TypeError, ValueError):
        return None


def get_market_snapshot() -> dict:
    """주요 글로벌 시장 지표 실시간 스냅샷."""
    results: dict = {}
    for name, symbol in _MARKET_TICKERS.items():
        try:
            fi = yf.Ticker(symbol).fast_info
            price = _fmt(fi.last_price)
            prev = _fmt(fi.previous_close)
            change = _fmt(price - prev) if price and prev else None
            change_pct = _fmt((price - prev) / prev * 100) if price and prev else None
            results[name] = {
                "symbol": symbol,
                "price": price,
                "change": change,
                "change_pct": change_pct,
            }
        except Exception as e:
            logger.warning(f"[finance] {name}({symbol}) 실패: {e}")
            results[name] = {"symbol": symbol, "error": "조회 실패"}
    results["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return results


def get_quote(ticker: str) -> dict:
    """단일 종목/지수 실시간 시세."""
    try:
        fi = yf.Ticker(ticker).fast_info
        price = _fmt(fi.last_price)
        prev = _fmt(fi.previous_close)
        change = _fmt(price - prev) if price and prev else None
        change_pct = _fmt((price - prev) / prev * 100) if price and prev else None
        return {
            "symbol": ticker,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        logger.error(f"[finance] {ticker} 조회 실패: {e}")
        return {"symbol": ticker, "error": str(e)}


def dispatch(tool: str, args: dict) -> dict:
    if tool == "get_market_snapshot":
        return get_market_snapshot()
    if tool == "get_quote":
        return get_quote(args.get("ticker", ""))
    return {"error": f"알 수 없는 finance 도구: {tool}"}
