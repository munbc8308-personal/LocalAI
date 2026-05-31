import logging

import chromadb

from core.embeddings import EmbeddingManager

from .document import Document
from .indexer import _COLLECTION_NAME

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5
_MIN_SCORE = 0.3  # cosine 거리 기준 — 낮을수록 유사


class Retriever:
    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        db_path: str = "./data/vectordb",
        top_k: int = _DEFAULT_TOP_K,
    ):
        self._embedder = embedding_manager
        self._top_k = top_k
        self._client = chromadb.PersistentClient(path=db_path)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def retrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        k = top_k or self._top_k
        query_embedding = self._embedder.embed_query(query).tolist()

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, max(self._collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )

        docs = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → 유사도 점수 변환
            score = 1.0 - dist
            if score >= _MIN_SCORE:
                docs.append(Document(page_content=text, metadata=meta, score=score))

        docs.sort(key=lambda d: d.score, reverse=True)
        logger.info(f"[retriever] '{query[:40]}...' → {len(docs)}개 문서")
        return docs

    async def aretrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        """nodes.py에서 await retriever.aretrieve(query) 형태로 호출."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.retrieve, query, top_k)
