import logging

from core.config import Settings

from .schemas import SearchResult
from .searxng import SearXNGClient
from .tavily import TavilyClient

logger = logging.getLogger(__name__)


class UnifiedSearchClient:
    """
    SearXNG → Tavily 순서로 폴백하는 통합 검색 클라이언트.
    nodes.py에서 search_client.search(query) 형태로 호출.
    """

    def __init__(self, settings: Settings):
        self._searxng = SearXNGClient(base_url=settings.searxng_url)
        self._tavily = TavilyClient(api_key=settings.tavily_api_key)
        self._use_searxng = True  # 첫 실패 후 비활성화 방지를 위한 상태 추적

    async def search(self, query: str) -> list[dict]:
        """
        검색 결과를 nodes.py가 기대하는 dict 리스트로 반환.
        keys: title, url, snippet
        """
        results: list[SearchResult] = []

        if self._use_searxng:
            results = await self._searxng.search(query)
            if not results:
                logger.info("[search] SearXNG 결과 없음 → Tavily 폴백")
                results = await self._tavily.search(query)
        else:
            results = await self._tavily.search(query)

        return [
            {"title": r.title, "url": r.url, "snippet": r.snippet}
            for r in results
        ]

    async def warmup(self) -> None:
        """앱 시작 시 SearXNG 가용 여부 확인."""
        available = await self._searxng.is_available()
        if not available:
            logger.warning("[search] SearXNG 미응답 — Tavily 전용 모드로 동작")
            self._use_searxng = False
        else:
            logger.info("[search] SearXNG 연결 확인")

    async def close(self) -> None:
        await self._searxng.close()
