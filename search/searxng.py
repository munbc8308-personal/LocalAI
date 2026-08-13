import logging

import httpx

from .schemas import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0
_DEFAULT_MAX_RESULTS = 15


class SearXNGClient:
    """
    자체 호스팅 SearXNG JSON API 클라이언트.
    SearXNG 실행: docker run -d -p 8080:8080 searxng/searxng
    """

    def __init__(self, base_url: str = "http://localhost:8080", max_results: int = _DEFAULT_MAX_RESULTS):
        self._base_url = base_url.rstrip("/")
        self._max_results = max_results
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def search(self, query: str) -> list[SearchResult]:
        try:
            response = await self._client.get(
                f"{self._base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "language": "auto",
                },
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.warning(f"[searxng] 요청 실패: {e}")
            return []

        results = []
        for item in data.get("results", [])[: self._max_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                )
            )

        logger.info(f"[searxng] '{query[:40]}' → {len(results)}개 결과")
        return results

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(f"{self._base_url}/healthz", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self._client.aclose()
