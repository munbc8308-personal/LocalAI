import hashlib
import logging
from pathlib import Path

import chromadb

from core.embeddings import EmbeddingManager

from .chunker import Chunker
from .document import Document

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "localai_docs"


def _doc_id(source: str, chunk_id: int) -> str:
    key = f"{source}::{chunk_id}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class Indexer:
    def __init__(self, embedding_manager: EmbeddingManager, db_path: str = "./data/vectordb"):
        self._embedder = embedding_manager
        self._client = chromadb.PersistentClient(path=db_path)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._chunker = Chunker()

    # ── 인덱싱 ────────────────────────────────────────────────────────────────

    def index_file(self, path: str | Path) -> int:
        docs = self._chunker.load_and_chunk(path)
        return self._upsert(docs)

    def index_directory(self, directory: str | Path) -> int:
        docs = self._chunker.load_directory(directory)
        return self._upsert(docs)

    def index_text(self, text: str, source: str = "manual") -> int:
        docs = [Document(page_content=text, metadata={"source": source, "chunk_id": 0})]
        return self._upsert(docs)

    def _upsert(self, docs: list[Document]) -> int:
        if not docs:
            return 0

        texts = [d.page_content for d in docs]
        embeddings = self._embedder.embed_documents(texts).tolist()
        ids = [_doc_id(d.source, d.chunk_id) for d in docs]
        metadatas = [d.metadata for d in docs]

        self._collection.upsert(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info(f"[indexer] {len(docs)}개 청크 upsert 완료")
        return len(docs)

    # ── 삭제 ──────────────────────────────────────────────────────────────────

    def delete_source(self, source: str) -> None:
        results = self._collection.get(where={"source": source})
        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            logger.info(f"[indexer] {source} — {len(results['ids'])}개 청크 삭제")

    def clear(self) -> None:
        self._client.delete_collection(_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("[indexer] 컬렉션 전체 초기화")

    # ── 통계 ──────────────────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        return self._collection.count()
