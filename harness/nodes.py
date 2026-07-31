import asyncio
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime

from core.config import AgentRole, get_settings
from core.model import ModelManager

# 시간민감 키워드 — 감지 시 "direct" 라우트를 "search"로 오버라이드
_TIME_SENSITIVE_RE = re.compile(
    r"최근|현재|지금|오늘|어제|이번\s*[주달년]?|작년|올해|최신|뉴스|트렌드|동향|"
    r"주가|환율|금리|물가|유가|비트코인|코인|암호화폐|"
    r"발표|출시|업데이트|릴리즈|버전|패치|업그레이드|"
    r"사건|사고|날씨|기온|기상|"
    r"선거|정치|법안|규제|정책|"
    r"실적|매출|영업이익|상장|ipo",
    re.IGNORECASE,
)

from tools.orchard import dispatch as orchard_dispatch
from tools.google import dispatch as google_dispatch, TOOL_NAMES as _GOOGLE_TOOL_NAMES
from tools.finance import dispatch as finance_dispatch, TOOL_NAMES as _FINANCE_TOOL_NAMES, _FINANCE_KEYWORDS

from .prompts import (
    CODE_SYSTEM,
    JUDGE_SYSTEM,
    ORCHESTRATOR_SYSTEM,
    RAG_SYSTEM,
    SEARCH_SYSTEM,
    SYNTHESIZE_SYSTEM,
    TOOLS_SYSTEM,
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
        now = datetime.now()
        location = get_settings().user_location
        ctx = (
            f"[현재 날짜: {now.strftime('%Y년 %m월 %d일')}] "
            f"[현재 시각: {now.strftime('%H:%M')}] "
            f"[사용자 위치: {location}]"
        )
        augmented_query = f"{ctx}\n\n{state['query']}"

        model = model_manager.get(AgentRole.ORCHESTRATOR)
        messages = [
            {"role": "system", "content": ORCHESTRATOR_SYSTEM},
            *state["messages"],
            {"role": "user", "content": augmented_query},
        ]
        raw = await model.generate(messages, temperature=0.2)
        try:
            parsed = _extract_json(raw)
            route = parsed.get("route", "direct")
            if route not in ("rag", "search", "code", "rag+search", "tools", "direct"):
                route = "direct"
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"오케스트레이터 JSON 파싱 실패: {raw[:200]}")
            route = "direct"
            parsed = {}

        # 시간민감 키워드 감지 → "direct" 라우트를 "search"로 오버라이드
        if route == "direct" and _TIME_SENSITIVE_RE.search(state["query"]):
            route = "search"
            if not parsed.get("subquery_search"):
                parsed["subquery_search"] = state["query"]
            logger.info("[orchestrator] 시간민감 키워드 감지 → route 오버라이드: direct → search")

        logger.info(f"[orchestrator] route={route}")
        return {
            "route": route,
            "subquery_rag": parsed.get("subquery_rag", state["query"]),
            "subquery_search": parsed.get("subquery_search", state["query"]),
            "subquery_tools": parsed.get("subquery_tools", state["query"]),
            "iteration": state.get("iteration", 0),
        }

    # ── RAG ───────────────────────────────────────────────────────────────────
    async def _do_retrieve(query: str) -> str:
        """RAG 검색 내부 로직 — retrieve / retrieve_and_search 공유."""
        if rag_retriever is None:
            logger.warning("[rag] retriever 미연결 — 빈 컨텍스트 반환")
            return ""
        docs = await rag_retriever.aretrieve(query)
        if not docs:
            return ""
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
        return summary

    async def retrieve(state: HarnessState) -> dict:
        query = state.get("subquery_rag") or state["query"]
        return {"rag_context": await _do_retrieve(query)}

    # ── Web Search ────────────────────────────────────────────────────────────
    async def _do_web_search(query: str) -> str:
        """웹 검색 내부 로직 — web_search / retrieve_and_search 공유.
        금융 키워드 감지 시 yfinance 실시간 데이터를 검색 결과 앞에 주입."""
        if search_client is None:
            logger.warning("[search] client 미연결 — 빈 컨텍스트 반환")
            return ""

        finance_prefix = ""
        if _FINANCE_KEYWORDS.search(query):
            try:
                loop = asyncio.get_event_loop()
                snap = await loop.run_in_executor(None, finance_dispatch, "get_market_snapshot", {})
                lines = []
                for name, data in snap.items():
                    if name == "as_of":
                        continue
                    if "error" in data:
                        continue
                    price = data.get("price")
                    change_pct = data.get("change_pct")
                    sign = "+" if (change_pct or 0) >= 0 else ""
                    lines.append(f"{name}: {price} ({sign}{change_pct}%)")
                if lines:
                    finance_prefix = f"[실시간 시장 데이터 — {snap.get('as_of', '')}]\n" + "\n".join(lines) + "\n\n"
                    logger.info(f"[finance] 시장 데이터 주입 완료 ({len(lines)}개 지표)")
            except Exception as e:
                logger.warning(f"[finance] 시장 데이터 주입 실패: {e}")

        results = await search_client.search(query)
        raw_context = "\n\n".join(
            f"[{r['title']}]({r['url']})\n{r['snippet']}" for r in results
        )

        model = model_manager.get(AgentRole.SEARCH)
        messages = [
            {"role": "system", "content": SEARCH_SYSTEM},
            {"role": "user", "content": f"Query: {query}\n\nSearch results:\n{finance_prefix}{raw_context}"},
        ]
        summary = await model.generate(messages)
        logger.info(f"[search] {len(results)}개 결과 처리 완료")
        return summary

    async def web_search(state: HarnessState) -> dict:
        query = state.get("subquery_search") or state["query"]
        return {"search_context": await _do_web_search(query)}

    # ── RAG + Web Search 병렬 ─────────────────────────────────────────────────
    async def retrieve_and_search(state: HarnessState) -> dict:
        """rag+search 라우트: retrieve와 web_search를 병렬 실행."""
        rag_query = state.get("subquery_rag") or state["query"]
        search_query = state.get("subquery_search") or state["query"]
        rag_ctx, search_ctx = await asyncio.gather(
            _do_retrieve(rag_query),
            _do_web_search(search_query),
        )
        return {"rag_context": rag_ctx, "search_context": search_ctx}

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

    # ── Tool Call (orchard) ───────────────────────────────────────────────────
    async def tool_call(state: HarnessState) -> dict:
        intent = state.get("subquery_tools") or state["query"]

        # 소형 모델로 intent → tool+args JSON 변환
        now = datetime.now()
        model = model_manager.get(AgentRole.SEARCH)
        messages = [
            {"role": "system", "content": TOOLS_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"[현재 날짜: {now.strftime('%Y년 %m월 %d일')}] "
                    f"[현재 시각: {now.strftime('%H:%M')}]\n\n{intent}"
                ),
            },
        ]
        raw = await model.generate(messages, temperature=0.1)

        try:
            parsed = _extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"[tool_call] JSON 파싱 실패: {raw[:200]}")
            return {"tool_context": f"도구 파싱 실패: {raw[:300]}"}

        # 단일 도구 or 복수 도구
        calls = parsed.get("tools") or ([{"tool": parsed["tool"], "args": parsed.get("args", {})}] if "tool" in parsed else [])
        if not calls:
            return {"tool_context": "실행할 도구를 결정하지 못했습니다."}

        results = []
        for call in calls:
            tool_name = call.get("tool", "")
            tool_args = call.get("args", {})
            logger.info(f"[tool_call] {tool_name}({tool_args})")
            if tool_name in _FINANCE_TOOL_NAMES:
                fn = finance_dispatch
            elif tool_name in _GOOGLE_TOOL_NAMES:
                fn = google_dispatch
            else:
                fn = orchard_dispatch
            result = await asyncio.get_event_loop().run_in_executor(
                None, fn, tool_name, tool_args
            )
            results.append({"tool": tool_name, "result": result})

        context = "\n\n".join(
            f"[{r['tool']}]\n{json.dumps(r['result'], ensure_ascii=False, indent=2)}"
            for r in results
        )
        logger.info(f"[tool_call] {len(results)}개 도구 실행 완료")
        return {"tool_context": context}

    # ── Synthesize ────────────────────────────────────────────────────────────
    async def synthesize(state: HarnessState) -> dict:
        parts = []
        if state.get("rag_context"):
            parts.append(f"[문서 검색 결과]\n{state['rag_context']}")
        if state.get("search_context"):
            parts.append(f"[웹 검색 결과]\n{state['search_context']}")
        if state.get("tool_context"):
            parts.append(f"[도구 실행 결과]\n{state['tool_context']}")
        if state.get("code_result"):
            return {
                "final_response": state["code_result"],
                "messages": [{"role": "assistant", "content": state["code_result"]}],
            }

        now = datetime.now()
        location = get_settings().user_location
        ctx = (
            f"[현재 날짜: {now.strftime('%Y년 %m월 %d일')}] "
            f"[현재 시각: {now.strftime('%H:%M')}] "
            f"[사용자 위치: {location}]"
        )
        context_block = "\n\n".join(parts)
        user_content = (
            f"{ctx}\n\nContext:\n{context_block}\n\nQuestion: {state['query']}"
            if context_block
            else f"{ctx}\n\n{state['query']}"
        )

        # Judge 피드백이 있으면 재시도에 반영
        iteration = state.get("iteration", 0)
        feedback = state.get("judge_feedback", "")
        if iteration > 0 and feedback:
            user_content += f"\n\n[이전 응답 개선 요청]: {feedback}\n위 피드백을 반드시 반영하여 더 나은 응답을 작성하세요."

        model = model_manager.get(AgentRole.SUMMARY)
        messages = [
            {"role": "system", "content": SYNTHESIZE_SYSTEM},
            *state["messages"],
            {"role": "user", "content": user_content},
        ]
        response = await model.generate(messages)

        # thinking 토큰이 전체 max_tokens를 소진한 경우 — 빈 응답 fallback
        if not response:
            logger.warning("[synthesize] 빈 응답 — thinking 토큰 초과 추정, fallback 반환")
            response = "죄송합니다, 응답을 생성하지 못했습니다. 다시 질문해 주세요."

        logger.info(f"[synthesize] 응답 합성 완료 (iteration={iteration}, len={len(response)})")
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
        "retrieve_and_search": retrieve_and_search,
        "code_gen": code_gen,
        "tool_call": tool_call,
        "synthesize": synthesize,
        "judge": judge,
    }
