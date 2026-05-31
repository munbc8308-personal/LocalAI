from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    manager = request.app.state.model_manager
    models_ready = getattr(request.app.state, "models_ready", False)
    return {
        "status": "ok" if models_ready else "degraded",
        "models_ready": models_ready,
        "loaded_models": [r.value for r in manager.loaded_roles],
    }
