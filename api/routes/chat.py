import asyncio
import json
import logging
import time
import uuid
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.dependencies import get_graph, get_session
from api.schemas import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    ChunkChoice,
    Choice,
    DeltaMessage,
    ResponseMessage,
    Usage,
)
from harness.memory import ConversationMemory
from harness.state import HarnessState

logger = logging.getLogger(__name__)
router = APIRouter()

_CHUNK_SIZE = 4  # 스트리밍 시 한 번에 전송할 단어 수


def _build_initial_state(request: ChatRequest, session: ConversationMemory) -> HarnessState:
    """ChatRequest + 세션 히스토리를 LangGraph 초기 상태로 변환."""
    # 마지막 user 메시지를 query로, 나머지는 히스토리로
    user_messages = [m for m in request.messages if m.role == "user"]
    query = user_messages[-1].content if user_messages else ""

    # 시스템 메시지 + 세션 히스토리 + 이번 요청 메시지 병합
    history = session.get()
    new_messages = [{"role": m.role, "content": m.content} for m in request.messages]

    return HarnessState(
        messages=history + new_messages,
        query=query,
        route="",
        subquery_rag="",
        subquery_search="",
        subquery_tools="",
        rag_context="",
        search_context="",
        code_result="",
        tool_context="",
        final_response="",
        judge_score=0.0,
        judge_feedback="",
        judge_pass=False,
        iteration=0,
        max_iterations=request.max_iterations,
    )


async def _run_graph(graph, state: HarnessState) -> str:
    try:
        async with asyncio.timeout(120):
            result = await graph.ainvoke(state)
    except asyncio.TimeoutError:
        logger.error("[chat] graph.ainvoke() 120초 초과")
        return "처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
    return result.get("final_response", "")


async def _sse_stream(
    graph,
    state: HarnessState,
    request_id: str,
    model_name: str,
) -> AsyncGenerator[str, None]:
    """
    그래프를 astream_events로 실행하고, synthesize 노드가 완료되면
    final_response를 청크 단위로 SSE 스트리밍.
    judge가 재시도를 요청하면 마지막 응답을 사용.
    """
    final_response = ""

    # role 청크 (스트리밍 시작 신호)
    first_chunk = ChatChunk(
        id=request_id,
        created=int(time.time()),
        model=model_name,
        choices=[ChunkChoice(index=0, delta=DeltaMessage(role="assistant"))],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    async for event in graph.astream_events(state, version="v2"):
        if event["event"] == "on_chain_end" and event["name"] == "synthesize":
            output = event["data"].get("output", {})
            candidate = output.get("final_response", "")
            if candidate:
                final_response = candidate

        # judge_pass=True 이벤트가 오면 현재 final_response를 스트리밍
        if event["event"] == "on_chain_end" and event["name"] == "judge":
            output = event["data"].get("output", {})
            if output.get("judge_pass") or output.get("iteration", 0) >= 2:
                break

    # 단어 단위로 청크 분할 전송
    words = final_response.split(" ")
    for i in range(0, len(words), _CHUNK_SIZE):
        chunk_words = words[i : i + _CHUNK_SIZE]
        content = " ".join(chunk_words)
        if i + _CHUNK_SIZE < len(words):
            content += " "

        chunk = ChatChunk(
            id=request_id,
            created=int(time.time()),
            model=model_name,
            choices=[ChunkChoice(index=0, delta=DeltaMessage(content=content))],
        )
        yield f"data: {chunk.model_dump_json()}\n\n"
        await asyncio.sleep(0)  # 이벤트 루프 양보

    # 종료 청크
    end_chunk = ChatChunk(
        id=request_id,
        created=int(time.time()),
        model=model_name,
        choices=[ChunkChoice(index=0, delta=DeltaMessage(), finish_reason="stop")],
    )
    yield f"data: {end_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatRequest,
    graph=Depends(get_graph),
    session: Annotated[ConversationMemory, Depends(get_session)] = None,
):
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    state = _build_initial_state(request, session)

    if request.stream:
        return StreamingResponse(
            _sse_stream(graph, state, request_id, request.model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming
    final_response = await _run_graph(graph, state)

    # 세션 히스토리 업데이트
    session.add("user", state["query"])
    session.add("assistant", final_response)

    return ChatResponse(
        id=request_id,
        model=request.model,
        choices=[Choice(message=ResponseMessage(content=final_response))],
        usage=Usage(),
    )
