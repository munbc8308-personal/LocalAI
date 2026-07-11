import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from harness import MemoryStore
from harness.state import HarnessState

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """메신저 종류에 무관한 공통 메시지 포맷."""
    session_id: str   # 채팅방/채널 ID
    user_id: str      # 발신자 ID
    text: str
    platform: str     # "telegram" | "discord" | "slack"


class BaseConnector(ABC):
    """모든 메신저 커넥터의 공통 인터페이스."""

    def __init__(self, graph, memory_store: MemoryStore):
        self._graph = graph
        self._memory_store = memory_store

    async def process(self, msg: IncomingMessage) -> str:
        """
        공통 처리 파이프라인:
        1. 세션 히스토리 로드
        2. 하네스 그래프 실행
        3. 세션 히스토리 업데이트
        4. 응답 반환
        """
        session = self._memory_store.get_or_create(msg.session_id)

        state = HarnessState(
            messages=session.get(),
            query=msg.text,
            route="",
            subquery_rag="",
            subquery_search="",
            subquery_tools="",
            rag_context="",
            search_context="",
            tool_context="",
            code_result="",
            final_response="",
            judge_score=0.0,
            judge_feedback="",
            judge_pass=False,
            iteration=0,
            max_iterations=2,
        )

        try:
            result = await self._graph.ainvoke(state)
            response = result.get("final_response") or "응답을 생성하지 못했습니다."
        except Exception as e:
            logger.error(f"[{msg.platform}] 그래프 실행 오류: {e}")
            response = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

        session.add("user", msg.text)
        session.add("assistant", response)
        return response

    @staticmethod
    def split_text(text: str, max_len: int) -> list[str]:
        """긴 응답을 플랫폼 최대 길이 단위로 분할."""
        if len(text) <= max_len:
            return [text]
        chunks, start = [], 0
        while start < len(text):
            end = start + max_len
            # 단어 경계에서 자르기
            if end < len(text) and " " in text[start:end]:
                end = text.rfind(" ", start, end) + 1
            chunks.append(text[start:end].strip())
            start = end
        return [c for c in chunks if c]

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
