import logging
from collections import deque

logger = logging.getLogger(__name__)

_MAX_TURNS = 20        # 세션당 최대 보관 턴 수
_SUMMARY_THRESHOLD = 16  # 이 턴 이상이면 오래된 히스토리 압축


class ConversationMemory:
    """
    세션별 대화 히스토리 관리.
    - 최근 _MAX_TURNS 턴을 메모리에 유지
    - _SUMMARY_THRESHOLD 초과 시 앞부분을 한 줄 요약으로 압축
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._history: deque[dict] = deque(maxlen=_MAX_TURNS)

    def add(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    def get(self) -> list[dict]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()

    def compress(self, summary: str) -> None:
        """오케스트레이터가 요약을 생성한 경우 히스토리를 압축."""
        self._history.clear()
        self._history.append({"role": "system", "content": f"[이전 대화 요약] {summary}"})
        logger.info(f"[memory:{self.session_id}] 히스토리 압축 완료")

    @property
    def turn_count(self) -> int:
        return len(self._history) // 2

    @property
    def needs_compression(self) -> bool:
        return len(self._history) >= _SUMMARY_THRESHOLD


class MemoryStore:
    """전체 세션 메모리 저장소 (인메모리, 추후 Redis/DB로 교체 가능)."""

    def __init__(self):
        self._sessions: dict[str, ConversationMemory] = {}

    def get_or_create(self, session_id: str) -> ConversationMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationMemory(session_id)
        return self._sessions[session_id]

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)
