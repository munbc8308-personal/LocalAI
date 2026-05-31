import asyncio
import logging

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import Settings

logger = logging.getLogger(__name__)

# nomic-embed-text는 prefix를 붙여야 성능이 제대로 나옴
_QUERY_PREFIX = "search_query: "
_DOC_PREFIX = "search_document: "


class EmbeddingManager:
    """nomic-embed-text 기반 임베딩 매니저."""

    def __init__(self, settings: Settings):
        self._model_name = settings.embedding_model
        self._model: SentenceTransformer | None = None

    def load(self) -> None:
        logger.info(f"임베딩 모델 로드 중: {self._model_name}")
        self._model = SentenceTransformer(self._model_name, trust_remote_code=True)
        logger.info("임베딩 모델 로드 완료")

    def _ensure_loaded(self) -> SentenceTransformer:
        if self._model is None:
            raise RuntimeError("임베딩 모델 미로드 — load() 먼저 호출 필요")
        return self._model

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """문서 청크 임베딩 — RAG 인덱싱 시 사용."""
        model = self._ensure_loaded()
        prefixed = [_DOC_PREFIX + t for t in texts]
        return model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)

    def embed_query(self, text: str) -> np.ndarray:
        """검색 쿼리 임베딩 — RAG 검색 시 사용."""
        model = self._ensure_loaded()
        return model.encode(_QUERY_PREFIX + text, normalize_embeddings=True)

    async def async_embed_documents(self, texts: list[str]) -> np.ndarray:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)

    async def async_embed_query(self, text: str) -> np.ndarray:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)
