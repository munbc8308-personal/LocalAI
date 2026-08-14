from langgraph.graph import END, START, StateGraph

from core.model import ModelManager

from .nodes import make_nodes
from .state import HarnessState

_MAX_ITERATIONS = 2


def _route_after_orchestrator(state: HarnessState) -> str:
    route = state.get("route", "direct")
    match route:
        case "rag":
            return "retrieve"
        case "search":
            return "web_search"
        case "code":
            return "code_gen"
        case "rag+search":
            return "retrieve_and_search"  # 병렬 실행
        case "tools":
            return "tool_call"
        case _:
            return "synthesize"


def _route_after_synthesize(state: HarnessState) -> str:
    # judge는 rag/rag+search 문서 기반 답변에만 사용 — 나머지 2-3s 절감
    if state.get("route") in ("code", "direct", "search", "tools"):
        return END
    return "judge"


def _route_after_judge(state: HarnessState) -> str:
    max_iter = state.get("max_iterations", _MAX_ITERATIONS)
    if state.get("judge_pass") or state.get("iteration", 0) >= max_iter:
        return END
    return "orchestrate"


def build_graph(
    model_manager: ModelManager,
    rag_retriever=None,
    search_client=None,
):
    """
    그래프 흐름:
      START
        → orchestrate  (라우팅 결정)
        → retrieve?    (RAG 컨텍스트)
        → web_search?  (웹 검색 컨텍스트)
        → code_gen?    (코드 생성)
        → synthesize   (최종 응답 합성)
        → judge        (품질 평가)
        → END          (통과) 또는 orchestrate (재시도, 최대 2회)
    """
    nodes = make_nodes(model_manager, rag_retriever, search_client)

    builder = StateGraph(HarnessState)

    for name, fn in nodes.items():
        builder.add_node(name, fn)

    builder.add_edge(START, "orchestrate")
    builder.add_conditional_edges("orchestrate", _route_after_orchestrator)
    builder.add_edge("retrieve", "synthesize")
    builder.add_edge("web_search", "synthesize")
    builder.add_edge("retrieve_and_search", "synthesize")
    builder.add_edge("code_gen", "synthesize")
    builder.add_edge("tool_call", "synthesize")
    builder.add_conditional_edges("synthesize", _route_after_synthesize)
    builder.add_conditional_edges("judge", _route_after_judge)

    return builder.compile()
