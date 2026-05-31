import logging

from .schemas import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RESULTS = 6


class TavilyClient:
    """
    Tavily API 클라이언트 — SearXNG 불가 시 폴백으로 사용.
    TAVILY_API_KEY 환경변수 필요.
    """

    def __init__(self, api_key: str, max_results: int = _DEFAULT_MAX_RESULTS):
        self._api_key = api_key
        self._max_results = max_results
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from tavily import AsyncTavilyClient
                self._client = AsyncTavilyClient(api_key=self._api_key)
            except ImportError:
                raise RuntimeError("tavily-python 패키지 필요: pip install tavily-python")
        return self._client

    async def search(self, query: str) -> list[SearchResult]:
        if not self._api_key:
            logger.warning("[tavily] API 키 미설정 — 빈 결과 반환")
            return []

        try:
            client = self._get_client()
            response = await client.search(
                query,
                max_results=self._max_results,
                search_depth="basic",
            )
        except Exception as e:
            logger.warning(f"[tavily] 요청 실패: {e}")
            return []

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            )
            for r in response.get("results", [])
        ]
        logger.info(f"[tavily] '{query[:40]}' → {len(results)}개 결과")
        return results
