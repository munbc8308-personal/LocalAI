import operator
from typing import Annotated, TypedDict


class HarnessState(TypedDict):
    # 대화 히스토리 — 노드마다 누적
    messages: Annotated[list[dict], operator.add]

    # 현재 요청
    query: str

    # 오케스트레이터 결정
    # "rag" | "search" | "code" | "rag+search" | "direct"
    route: str
    subquery_rag: str     # RAG용 최적화 쿼리
    subquery_search: str  # 웹검색용 최적화 쿼리

    # 각 에이전트 결과
    rag_context: str
    search_context: str
    code_result: str

    # 최종 합성 결과
    final_response: str

    # Judge 평가
    judge_score: float    # 0.0 ~ 1.0
    judge_feedback: str
    judge_pass: bool

    # 반성 루프 제어
    iteration: int        # 최대 2회
