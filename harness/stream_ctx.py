"""
Synthesize 노드 스트리밍용 ContextVar.
asyncio.create_task()가 컨텍스트를 복사하므로 태스크별로 독립적인 큐를 가짐.
"""
import asyncio
from contextvars import ContextVar

_stream_queue_var: ContextVar[asyncio.Queue | None] = ContextVar("stream_queue", default=None)


def set_stream_queue(q: asyncio.Queue) -> None:
    _stream_queue_var.set(q)


def clear_stream_queue() -> None:
    _stream_queue_var.set(None)


def get_stream_queue() -> asyncio.Queue | None:
    return _stream_queue_var.get()
