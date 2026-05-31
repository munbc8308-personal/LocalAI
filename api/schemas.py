import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field


def _new_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


# ── 요청 ─────────────────────────────────────────────────────────────────────

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str = "localai"
    messages: list[Message]
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)


# ── 응답 (non-streaming) ──────────────────────────────────────────────────────

class ResponseMessage(BaseModel):
    role: str = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    id: str = Field(default_factory=_new_id)
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "localai"
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


# ── 응답 (SSE streaming chunk) ────────────────────────────────────────────────

class DeltaMessage(BaseModel):
    role: str | None = None
    content: str | None = None


class ChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "localai"
    choices: list[ChunkChoice]


# ── 모델 목록 ─────────────────────────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "localai"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]
