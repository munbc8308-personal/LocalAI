from typing import Annotated

from fastapi import Depends, Header, Request

from core.model import ModelManager
from harness import MemoryStore
from harness.memory import ConversationMemory


def get_model_manager(request: Request) -> ModelManager:
    return request.app.state.model_manager


def get_graph(request: Request):
    return request.app.state.graph


def get_memory_store(request: Request) -> MemoryStore:
    return request.app.state.memory_store


def get_session(
    memory_store: Annotated[MemoryStore, Depends(get_memory_store)],
    x_session_id: Annotated[str | None, Header()] = None,
) -> ConversationMemory:
    """X-Session-ID 헤더로 세션 식별. 없으면 stateless 임시 세션 사용."""
    session_id = x_session_id or "default"
    return memory_store.get_or_create(session_id)
