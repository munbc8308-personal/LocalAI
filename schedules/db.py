import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path("./data/schedules.db")


@dataclass
class Schedule:
    name: str
    topic: str
    hour: int
    minute: int
    chat_id: str
    active: bool = True
    id: int | None = None
    created_at: str = ""
    last_run_at: str | None = None
    last_status: str | None = None


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                topic       TEXT    NOT NULL,
                hour        INTEGER NOT NULL,
                minute      INTEGER NOT NULL,
                chat_id     TEXT    NOT NULL,
                active      INTEGER DEFAULT 1,
                created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
                last_run_at TEXT,
                last_status TEXT
            )
        """)


def list_schedules() -> list[Schedule]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM schedules ORDER BY id DESC").fetchall()
    return [_to_schedule(r) for r in rows]


def get_schedule(schedule_id: int) -> Schedule | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return _to_schedule(row) if row else None


def create_schedule(s: Schedule) -> Schedule:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO schedules (name, topic, hour, minute, chat_id, active) VALUES (?,?,?,?,?,?)",
            (s.name, s.topic, s.hour, s.minute, s.chat_id, int(s.active)),
        )
        new_id = cur.lastrowid
    return get_schedule(new_id)


def update_schedule(s: Schedule) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE schedules SET name=?, topic=?, hour=?, minute=?, chat_id=?, active=? WHERE id=?",
            (s.name, s.topic, s.hour, s.minute, s.chat_id, int(s.active), s.id),
        )


def delete_schedule(schedule_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


def toggle_active(schedule_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT active FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        if not row:
            raise ValueError(f"스케줄 {schedule_id} 없음")
        new_active = not bool(row["active"])
        conn.execute("UPDATE schedules SET active=? WHERE id=?", (int(new_active), schedule_id))
    return new_active


def update_run_status(schedule_id: int, status: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _conn() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_at=?, last_status=? WHERE id=?",
            (now, status, schedule_id),
        )


def _to_schedule(row: sqlite3.Row) -> Schedule:
    return Schedule(
        id=row["id"],
        name=row["name"],
        topic=row["topic"],
        hour=row["hour"],
        minute=row["minute"],
        chat_id=row["chat_id"],
        active=bool(row["active"]),
        created_at=row["created_at"] or "",
        last_run_at=row["last_run_at"],
        last_status=row["last_status"],
    )
