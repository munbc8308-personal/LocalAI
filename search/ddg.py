import logging

from .schemas import SearchResult

logger = logging.getLogger(__name__)


class DDGClient:
    """DuckDuckGo 검색 — API 키 불필요, SearXNG·Tavily 모두 실패 시 폴백."""

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError:
            logger.warning("[ddg] ddgs 패키지 미설치 — 빈 결과 반환")
            return []

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                    ))
            logger.info(f"[ddg] {len(results)}개 결과")
            return results
        except Exception as e:
            logger.warning(f"[ddg] 검색 실패: {e}")
            return []
