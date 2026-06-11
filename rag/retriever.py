import asyncio
import logging
import re

import numpy as np
import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

from core.embeddings import EmbeddingManager
from .document import Document
from .indexer import _COLLECTION_NAME

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5
_MIN_VECTOR_SCORE = 0.2   # 초기 벡터 검색 임계값 (리랭킹 전이므로 관대하게)
_EXPAND_FACTOR = 4         # top_k * factor = 초기 후보 수
_RRF_K = 60               # Reciprocal Rank Fusion 상수
_RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


def _tokenize(text: str) -> list[str]:
    """한국어·영어 혼용 텍스트 토크나이징 (공백 + 구두점 분리)."""
    text = re.sub(r"[^\w\s가-힣]", " ", text.lower())
    return [t for t in text.split() if t]


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

        # BM25 인덱스 (문서 추가/삭제 시 자동 재빌드)
        self._bm25: BM25Okapi | None = None
        self._bm25_texts: list[str] = []
        self._bm25_ids: list[str] = []
        self._bm25_count: int = -1

        # Cross-encoder 리랭커 (다국어 — 한국어 포함)
        self._reranker: CrossEncoder | None = None
        try:
            logger.info(f"[retriever] 리랭커 로드 중: {_RERANKER_MODEL}")
            self._reranker = CrossEncoder(_RERANKER_MODEL)
            logger.info("[retriever] 리랭커 로드 완료")
        except Exception as e:
            logger.warning(f"[retriever] 리랭커 로드 실패 — 벡터 검색만 사용: {e}")

    # ── BM25 ──────────────────────────────────────────────────────────────────

    def _ensure_bm25(self) -> None:
        """컬렉션이 변경됐을 때만 BM25 인덱스를 재빌드."""
        count = self._collection.count()
        if count == self._bm25_count:
            return
        if count == 0:
            self._bm25 = None
            self._bm25_count = 0
            return

        logger.info(f"[retriever] BM25 인덱스 빌드 중 ({count}개 문서)...")
        results = self._collection.get(include=["documents"])
        self._bm25_texts = results["documents"]
        self._bm25_ids = results["ids"]
        tokenized = [_tokenize(t) for t in self._bm25_texts]
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_count = count
        logger.info("[retriever] BM25 인덱스 빌드 완료")

    def _bm25_search(self, query: str, k: int) -> list[tuple[str, str, float]]:
        """BM25 검색 → list[(id, text, score)]."""
        if not self._bm25:
            return []
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:k]
        return [
            (self._bm25_ids[i], self._bm25_texts[i], float(scores[i]))
            for i in top_indices
            if scores[i] > 0
        ]

    # ── Vector Search ─────────────────────────────────────────────────────────

    def _vector_search(self, query: str, k: int) -> list[tuple[str, str, float]]:
        """벡터 검색 → list[(id, text, score)]."""
        count = self._collection.count()
        if count == 0:
            return []
        query_embedding = self._embedder.embed_query(query).tolist()
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, count),
            include=["documents", "distances"],
        )
        out = []
        for doc_id, text, dist in zip(
            results["ids"][0], results["documents"][0], results["distances"][0]
        ):
            score = 1.0 - dist
            if score >= _MIN_VECTOR_SCORE:
                out.append((doc_id, text, score))
        return out

    # ── RRF Fusion ────────────────────────────────────────────────────────────

    @staticmethod
    def _rrf_fusion(
        vector_hits: list[tuple[str, str, float]],
        bm25_hits: list[tuple[str, str, float]],
    ) -> list[tuple[str, str]]:
        """Reciprocal Rank Fusion으로 두 결과 합산 → 중복 제거 후 정렬."""
        rrf_scores: dict[str, float] = {}
        texts: dict[str, str] = {}

        for rank, (doc_id, text, _) in enumerate(vector_hits):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            texts[doc_id] = text

        for rank, (doc_id, text, _) in enumerate(bm25_hits):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            texts[doc_id] = text

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [(doc_id, texts[doc_id]) for doc_id, _ in ranked]

    # ── Reranking ─────────────────────────────────────────────────────────────

    def _rerank(self, query: str, candidates: list[tuple[str, str]]) -> list[tuple[str, str, float]]:
        """Cross-encoder 리랭킹 → list[(id, text, score)] 점수 내림차순."""
        if not candidates or self._reranker is None:
            return [(doc_id, text, 0.0) for doc_id, text in candidates]
        pairs = [(query, text) for _, text in candidates]
        scores = np.atleast_1d(self._reranker.predict(pairs, show_progress_bar=False))
        ranked = sorted(
            zip(candidates, scores.tolist()),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(doc_id, text, float(score)) for (doc_id, text), score in ranked]

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        k = top_k or self._top_k
        expand_k = k * _EXPAND_FACTOR

        self._ensure_bm25()

        vector_hits = self._vector_search(query, expand_k)
        bm25_hits = self._bm25_search(query, expand_k)

        # 두 결과를 RRF로 합산
        fused = self._rrf_fusion(vector_hits, bm25_hits)
        candidates = fused[: k * 2]

        if not candidates:
            logger.info(f"[retriever] '{query[:40]}' → 결과 없음")
            return []

        # Cross-encoder 리랭킹
        reranked = self._rerank(query, candidates)[:k]

        # 메타데이터 일괄 조회
        top_ids = [doc_id for doc_id, _, _ in reranked]
        meta_result = self._collection.get(ids=top_ids, include=["metadatas"])
        id_to_meta = dict(zip(meta_result["ids"], meta_result["metadatas"]))

        docs = [
            Document(page_content=text, metadata=id_to_meta.get(doc_id, {}), score=score)
            for doc_id, text, score in reranked
        ]

        logger.info(
            f"[retriever] '{query[:40]}' → "
            f"vector:{len(vector_hits)} bm25:{len(bm25_hits)} "
            f"fused:{len(fused)} final:{len(docs)}"
        )
        return docs

    async def aretrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.retrieve, query, top_k)
