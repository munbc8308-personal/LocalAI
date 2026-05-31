import json
import logging
import re
from collections.abc import Callable

from core.config import AgentRole
from core.model import ModelManager

from .prompts import (
    CODE_SYSTEM,
    JUDGE_SYSTEM,
    ORCHESTRATOR_SYSTEM,
    RAG_SYSTEM,
    SEARCH_SYSTEM,
    SYNTHESIZE_SYSTEM,
)
from .state import HarnessState

logger = logging.getLogger(__name__)

# RAG / Search 클라이언트는 step 4에서 주입됨
_RagRetriever = object
_SearchClient = object


def _extract_json(text: str) -> dict:
    """LLM 출력에서 JSON 추출 — 마크다운 코드블록 포함 처리."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return {}


def make_nodes(
    model_manager: ModelManager,
    rag_retriever: _RagRetriever | None = None,
    search_client: _SearchClient | None = None,
) -> dict[str, Callable]:
    """
    ModelManager와 선택적 서비스를 받아 LangGraph 노드 함수 딕셔너리 반환.
    RAG/Search 클라이언트가 없으면 해당 노드는 빈 컨텍스트를 반환.
    """

    # ── Orchestrator ──────────────────────────────────────────────────────────
    async def orchestrate(state: HarnessState) -> dict:
        model = model_manager.get(AgentRole.ORCHESTRATOR)
        messages = [
            {"role": "system", "content": ORCHESTRATOR_SYSTEM},
            *state["messages"],
            {"role": "user", "content": state["query"]},
        ]
        raw = await model.generate(messages, temperature=0.2)
        try:
            parsed = _extract_json(raw)
            route = parsed.get("route", "direct")
            if route not in ("rag", "search", "code", "rag+search", "direct"):
                route = "direct"
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"오케스트레이터 JSON 파싱 실패: {raw[:200]}")
            route = "direct"
            parsed = {}

        logger.info(f"[orchestrator] route={route}")
        return {
            "route": route,
            "subquery_rag": parsed.get("subquery_rag", state["query"]),
            "subquery_search": parsed.get("subquery_search", state["query"]),
            "iteration": state.get("iteration", 0),
        }

    # ── RAG ───────────────────────────────────────────────────────────────────
    async def retrieve(state: HarnessState) -> dict:
        query = state.get("subquery_rag") or state["query"]

        if rag_retriever is None:
            logger.warning("[rag] retriever 미연결 — 빈 컨텍스트 반환")
            return {"rag_context": ""}

        docs = await rag_retriever.aretrieve(query)
        context = "\n\n---\n\n".join(
            f"[{i + 1}] {d.page_content}" for i, d in enumerate(docs)
        )

        model = model_manager.get(AgentRole.RAG)
        messages = [
            {"role": "system", "content": RAG_SYSTEM},
            {"role": "user", "content": f"Query: {query}\n\nDocuments:\n{context}"},
        ]
        summary = await model.generate(messages)
        logger.info(f"[rag] {len(docs)}개 문서 검색 완료")
        return {"rag_context": summary}

    # ── Web Search ────────────────────────────────────────────────────────────
    async def web_search(state: HarnessState) -> dict:
        query = state.get("subquery_search") or state["query"]

        if search_client is None:
            logger.warning("[search] client 미연결 — 빈 컨텍스트 반환")
            return {"search_context": ""}

        results = await search_client.search(query)
        raw_context = "\n\n".join(
            f"[{r['title']}]({r['url']})\n{r['snippet']}" for r in results
        )

        model = model_manager.get(AgentRole.SEARCH)
        messages = [
            {"role": "system", "content": SEARCH_SYSTEM},
            {"role": "user", "content": f"Query: {query}\n\nSearch results:\n{raw_context}"},
        ]
        summary = await model.generate(messages)
        logger.info(f"[search] {len(results)}개 결과 처리 완료")
        return {"search_context": summary}

    # ── Code ──────────────────────────────────────────────────────────────────
    async def code_gen(state: HarnessState) -> dict:
        model = model_manager.get(AgentRole.CODE)
        messages = [
            {"role": "system", "content": CODE_SYSTEM},
            *state["messages"],
            {"role": "user", "content": state["query"]},
        ]
        result = await model.generate(messages)
        logger.info("[code] 생성 완료")
        return {"code_result": result}

    # ── Synthesize ────────────────────────────────────────────────────────────
    async def synthesize(state: HarnessState) -> dict:
        parts = []
        if state.get("rag_context"):
            parts.append(f"[문서 검색 결과]\n{state['rag_context']}")
        if state.get("search_context"):
            parts.append(f"[웹 검색 결과]\n{state['search_context']}")
        if state.get("code_result"):
            return {
                "final_response": state["code_result"],
                "messages": [{"role": "assistant", "content": state["code_result"]}],
            }

        context_block = "\n\n".join(parts)
        user_content = (
            f"Context:\n{context_block}\n\nQuestion: {state['query']}"
            if context_block
            else state["query"]
        )

        model = model_manager.get(AgentRole.SUMMARY)
        messages = [
            {"role": "system", "content": SYNTHESIZE_SYSTEM},
            *state["messages"],
            {"role": "user", "content": user_content},
        ]
        response = await model.generate(messages)
        logger.info("[synthesize] 응답 합성 완료")
        return {
            "final_response": response,
            "messages": [{"role": "assistant", "content": response}],
        }

    # ── Judge ─────────────────────────────────────────────────────────────────
    async def judge(state: HarnessState) -> dict:
        model = model_manager.get(AgentRole.JUDGE)
        messages = [
            {"role": "system", "content": JUDGE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Query: {state['query']}\n\n"
                    f"Response: {state['final_response']}"
                ),
            },
        ]
        raw = await model.generate(messages, temperature=0.1)
        try:
            parsed = _extract_json(raw)
            score = float(parsed.get("score", 0.5))
            passed = bool(parsed.get("pass", score >= 0.8))
            feedback = parsed.get("feedback", "")
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"[judge] JSON 파싱 실패: {raw[:200]}")
            score, passed, feedback = 0.5, False, "평가 실패"

        logger.info(f"[judge] score={score:.2f} pass={passed} iteration={state.get('iteration', 0)}")
        return {
            "judge_score": score,
            "judge_pass": passed,
            "judge_feedback": feedback,
            "iteration": state.get("iteration", 0) + 1,
        }

    return {
        "orchestrate": orchestrate,
        "retrieve": retrieve,
        "web_search": web_search,
        "code_gen": code_gen,
        "synthesize": synthesize,
        "judge": judge,
    }
