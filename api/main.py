import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, documents, health, models
from core.config import get_settings
from core.embeddings import EmbeddingManager
from core.model import ModelManager
from connectors import ConnectorRunner
from harness import MemoryStore, build_graph
from rag import Indexer, Retriever
from schedules import init_db, start as sched_start, stop as sched_stop
from schedules.router import router as schedules_router
from search import UnifiedSearchClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    logger.info("=== LocalAI 시작 ===")

    # 모델 로드 (전체 병렬) — 실패해도 서버는 기동, /health로 상태 확인 가능
    model_manager = ModelManager(settings)
    models_ready = False
    try:
        await model_manager.load_all()
        models_ready = True
    except Exception as e:
        logger.error(f"[startup] 모델 로드 실패: {e}")
        if "401" in str(e) or "Unauthorized" in str(e) or "token" in str(e).lower():
            logger.warning(
                "[startup] HuggingFace 인증 필요 → "
                "'.venv/bin/huggingface-cli login' 실행 후 재시작"
            )
        logger.warning("[startup] 모델 없이 서버 기동 — /health 에서 상태 확인")

    # 임베딩 모델 로드
    embedding_manager = EmbeddingManager(settings)
    try:
        embedding_manager.load()
    except Exception as e:
        logger.warning(f"[startup] 임베딩 모델 로드 실패: {e}")

    # RAG 초기화
    retriever = Retriever(embedding_manager, db_path=settings.vector_db_path)
    indexer = Indexer(embedding_manager, db_path=settings.vector_db_path)
    try:
        logger.info(f"[rag] 인덱스 문서 수: {indexer.count}")
    except Exception:
        logger.warning("[rag] ChromaDB 초기화 지연")

    # Search 초기화
    search_client = UnifiedSearchClient(settings)
    await search_client.warmup()

    # 하네스 그래프 빌드 (RAG/Search 주입)
    graph = build_graph(model_manager, rag_retriever=retriever, search_client=search_client)

    # 메모리 스토어 초기화
    memory_store = MemoryStore()

    # 스케줄러 초기화 및 시작
    init_db()
    sched_start()

    # 메신저 커넥터 시작 (백그라운드 태스크)
    connector_runner = ConnectorRunner(
        settings=settings,
        graph=graph,
        memory_store=memory_store,
        indexer=indexer,
    )
    await connector_runner.start()

    # app.state에 등록 → 의존성 주입으로 접근
    app.state.model_manager = model_manager
    app.state.models_ready = models_ready
    app.state.embedding_manager = embedding_manager
    app.state.retriever = retriever
    app.state.indexer = indexer
    app.state.search_client = search_client
    app.state.graph = graph
    app.state.memory_store = memory_store

    logger.info(f"=== 준비 완료 (models_ready={models_ready}) — {settings.api_host}:{settings.api_port} ===")
    yield

    await connector_runner.stop()
    await search_client.close()
    sched_stop()
    logger.info("=== LocalAI 종료 ===")


def create_app() -> FastAPI:
    app = FastAPI(
        title="LocalAI",
        description="OpenAI 호환 로컬 AI 서비스",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["system"])
    app.include_router(models.router, tags=["models"])
    app.include_router(chat.router, tags=["chat"])
    app.include_router(documents.router, tags=["documents"])
    app.include_router(schedules_router, tags=["schedules"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
