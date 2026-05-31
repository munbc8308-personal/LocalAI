import logging
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader

from .document import Document

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".rst"}

_DEFAULT_CHUNK_SIZE = 512
_DEFAULT_CHUNK_OVERLAP = 64


class Chunker:
    def __init__(
        self,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    ):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )

    def load_and_chunk(self, path: str | Path) -> list[Document]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix not in _SUPPORTED_EXTENSIONS:
            raise ValueError(f"지원하지 않는 파일 형식: {path.suffix}")

        raw_docs = self._load(path)
        chunks = self._splitter.split_documents(raw_docs)

        documents = [
            Document(
                page_content=chunk.page_content,
                metadata={
                    **chunk.metadata,
                    "source": str(path),
                    "chunk_id": i,
                },
            )
            for i, chunk in enumerate(chunks)
        ]
        logger.info(f"[chunker] {path.name} → {len(documents)}개 청크")
        return documents

    def load_directory(self, directory: str | Path) -> list[Document]:
        directory = Path(directory)
        all_docs: list[Document] = []
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in _SUPPORTED_EXTENSIONS:
                try:
                    all_docs.extend(self.load_and_chunk(path))
                except Exception as e:
                    logger.warning(f"[chunker] {path.name} 스킵: {e}")
        logger.info(f"[chunker] 디렉토리 총 {len(all_docs)}개 청크")
        return all_docs

    @staticmethod
    def _load(path: Path):
        if path.suffix == ".pdf":
            return PyPDFLoader(str(path)).load()
        return TextLoader(str(path), encoding="utf-8").load()
