from dataclasses import dataclass, field


@dataclass
class Document:
    page_content: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0  # 검색 유사도 점수 (retriever에서 채워짐)

    @property
    def source(self) -> str:
        return self.metadata.get("source", "unknown")

    @property
    def chunk_id(self) -> int:
        return self.metadata.get("chunk_id", 0)
