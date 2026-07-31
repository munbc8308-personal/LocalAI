import logging
import sqlite3
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_TURNS = 20
_SUMMARY_THRESHOLD = 16
_DB_PATH = "./data/memory.db"


class ConversationMemory:
    """세션별 대화 히스토리 (in-memory deque + SQLite 영속화)."""

    def __init__(self, session_id: str, store: "MemoryStore"):
        self.session_id = session_id
        self._history: deque[dict] = deque(maxlen=_MAX_TURNS)
        self._store = store

    def add(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        self._store._persist_turn(self.session_id, role, content)

    def get(self) -> list[dict]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
        self._store._delete_session(self.session_id)

    def compress(self, summary: str) -> None:
        self._history.clear()
        entry = {"role": "system", "content": f"[이전 대화 요약] {summary}"}
        self._history.append(entry)
        self._store._delete_session(self.session_id)
        self._store._persist_turn(self.session_id, "system", entry["content"])
        logger.info(f"[memory:{self.session_id}] 히스토리 압축 완료")

    @property
    def turn_count(self) -> int:
        return len(self._history) // 2

    @property
    def needs_compression(self) -> bool:
        return len(self._history) >= _SUMMARY_THRESHOLD


class MemoryStore:
    """세션 메모리 저장소 — SQLite 영속화로 재시작 후에도 히스토리 유지."""

    def __init__(self, db_path: str = _DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ConversationMemory] = {}
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL DEFAULT (unixepoch('now', 'subsec'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON turns(session_id, id)")

    def _persist_turn(self, session_id: str, role: str, content: str) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO turns (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, role, content),
                )
                # 세션당 최근 MAX_TURNS * 2 행만 유지
                conn.execute("""
                    DELETE FROM turns WHERE session_id = ? AND id NOT IN (
                        SELECT id FROM turns WHERE session_id = ?
                        ORDER BY id DESC LIMIT ?
                    )
                """, (session_id, session_id, _MAX_TURNS))
        except Exception as e:
            logger.warning(f"[memory] SQLite 저장 실패: {e}")

    def _delete_session(self, session_id: str) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        except Exception as e:
            logger.warning(f"[memory] SQLite 삭제 실패: {e}")

    def get_or_create(self, session_id: str) -> ConversationMemory:
        if session_id not in self._sessions:
            mem = ConversationMemory(session_id, self)
            try:
                with sqlite3.connect(self._db_path) as conn:
                    rows = conn.execute(
                        "SELECT role, content FROM turns WHERE session_id = ? ORDER BY id LIMIT ?",
                        (session_id, _MAX_TURNS),
                    ).fetchall()
                for role, content in rows:
                    mem._history.append({"role": role, "content": content})
                if rows:
                    logger.info(f"[memory:{session_id}] SQLite에서 {len(rows)}개 턴 복원")
            except Exception as e:
                logger.warning(f"[memory] SQLite 로드 실패: {e}")
            self._sessions[session_id] = mem
        return self._sessions[session_id]

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._delete_session(session_id)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)
