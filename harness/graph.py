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
            return "retrieve"   # retrieve → web_search → synthesize 순서
        case _:
            return "synthesize"


def _route_after_retrieve(state: HarnessState) -> str:
    # rag+search 라우트일 때만 웹 검색도 수행
    if state.get("route") == "rag+search":
        return "web_search"
    return "synthesize"


def _route_after_judge(state: HarnessState) -> str:
    if state.get("judge_pass") or state.get("iteration", 0) >= _MAX_ITERATIONS:
        return END
    # 반성 루프: 오케스트레이터부터 재시도
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
    builder.add_conditional_edges("retrieve", _route_after_retrieve)
    builder.add_edge("web_search", "synthesize")
    builder.add_edge("code_gen", "synthesize")
    builder.add_edge("synthesize", "judge")
    builder.add_conditional_edges("judge", _route_after_judge)

    return builder.compile()
