from fastapi import APIRouter, Request

from api.schemas import ModelInfo, ModelList
from core.config import AgentRole

router = APIRouter()

_ROLE_MODEL_NAMES = {
    AgentRole.ORCHESTRATOR: "localai-orchestrator",
    AgentRole.CODE: "localai-code",
    AgentRole.RAG: "localai-rag",
    AgentRole.JUDGE: "localai-judge",
    AgentRole.SEARCH: "localai-search",
    AgentRole.SUMMARY: "localai-summary",
}


@router.get("/v1/models")
async def list_models(request: Request) -> ModelList:
    manager = request.app.state.model_manager
    data = [
        ModelInfo(id="localai"),  # 기본 통합 엔드포인트
        *[
            ModelInfo(id=_ROLE_MODEL_NAMES[role])
            for role in manager.loaded_roles
        ],
    ]
    return ModelList(data=data)
