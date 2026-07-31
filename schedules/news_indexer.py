import asyncio
import hashlib
import html
import logging
import re
from datetime import datetime, timedelta

import feedparser
import httpx

from rag.document import Document

logger = logging.getLogger(__name__)

_indexer = None

# 기본 RSS 피드 목록 — (이름, URL)
_DEFAULT_FEEDS: list[tuple[str, str]] = [
    ("Google뉴스_한국", "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"),
    ("BBC_코리아", "https://feeds.bbci.co.uk/korean/rss.xml"),
    ("Bloomberg_Markets", "https://feeds.bloomberg.com/markets/news.rss"),
    ("WSJ_World", "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("HackerNews", "https://hnrss.org/frontpage"),
]

_MAX_AGE_DAYS = 7
_MAX_ARTICLES_PER_FEED = 30


def set_indexer(indexer) -> None:
    global _indexer
    _indexer = indexer


async def _crawl_feed(client: httpx.AsyncClient, feed_name: str, url: str) -> list:
    """단일 RSS 피드 크롤 → Document 리스트 반환."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        docs = []
        for entry in feed.entries[:_MAX_ARTICLES_PER_FEED]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "").strip()
            published = _parse_date(entry)
            if not title or not link:
                continue
            summary = html.unescape(re.sub(r"<[^>]+>", "", summary)).strip()
            content = f"제목: {title}\n출처: {feed_name} ({published})\n\n{summary}"
            url_hash = hashlib.sha256(link.encode()).hexdigest()[:16]
            published_ts = int(published.replace("-", ""))
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": f"news::{url_hash}",
                    "type": "news",
                    "feed_name": feed_name,
                    "url": link,
                    "published_at": published,
                    "published_ts": published_ts,
                    "chunk_id": 0,
                },
            ))
        logger.info(f"[news_indexer] {feed_name}: {len(docs)}개 수집")
        return docs
    except Exception as e:
        logger.warning(f"[news_indexer] {feed_name} 크롤 실패: {e}")
        return []


async def crawl_and_index() -> None:
    if _indexer is None:
        logger.warning("[news_indexer] indexer 미연결 — 건너뜀")
        return

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # 5개 피드 병렬 크롤
        results = await asyncio.gather(
            *[_crawl_feed(client, name, url) for name, url in _DEFAULT_FEEDS],
            return_exceptions=True,
        )

    # 전체 합산 + 중복 제거
    seen: set[str] = set()
    all_docs = []
    for r in results:
        if isinstance(r, Exception):
            continue
        for d in r:
            if d.metadata["source"] not in seen:
                seen.add(d.metadata["source"])
                all_docs.append(d)

    if all_docs:
        _indexer.index_documents(all_docs)
        logger.info(f"[news_indexer] 완료 — 총 {len(all_docs)}개 인덱싱")
    else:
        logger.warning("[news_indexer] 인덱싱할 문서 없음")

    await _cleanup_old_news()


async def _cleanup_old_news() -> None:
    if _indexer is None:
        return
    # YYYYMMDD 정수로 비교 (ChromaDB $lt는 숫자만 지원)
    cutoff_ts = int((datetime.now() - timedelta(days=_MAX_AGE_DAYS)).strftime("%Y%m%d"))
    try:
        results = _indexer._collection.get(
            where={"$and": [{"type": {"$eq": "news"}}, {"published_ts": {"$lt": cutoff_ts}}]},
            include=[],
        )
        if results["ids"]:
            _indexer._collection.delete(ids=results["ids"])
            logger.info(f"[news_indexer] 만료 뉴스 {len(results['ids'])}개 삭제 (기준: {cutoff_ts})")
    except Exception as e:
        logger.warning(f"[news_indexer] 정리 실패: {e}")


def _parse_date(entry) -> str:
    if getattr(entry, "published_parsed", None):
        t = entry.published_parsed
        return datetime(*t[:6]).strftime("%Y-%m-%d")
    if getattr(entry, "updated_parsed", None):
        t = entry.updated_parsed
        return datetime(*t[:6]).strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")
