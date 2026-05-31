from enum import Enum
from functools import lru_cache

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    CODE = "code"
    RAG = "rag"
    JUDGE = "judge"
    SEARCH = "search"
    SUMMARY = "summary"


class ModelConfig(BaseModel):
    model_id: str
    max_tokens: int = 4096
    temperature: float = 0.7


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # 모델 ID
    orchestrator_model: str = "mlx-community/gemma-4-27b-it-8bit"
    code_model: str = "mlx-community/gemma-4-27b-it-8bit"
    rag_model: str = "mlx-community/gemma-4-12b-it-8bit"
    judge_model: str = "mlx-community/gemma-4-12b-it-4bit"
    search_model: str = "mlx-community/gemma-4-4b-it-8bit"
    summary_model: str = "mlx-community/gemma-4-4b-it-4bit"
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"

    # 추론 기본값
    max_tokens: int = 4096
    temperature: float = 0.7

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 검색
    searxng_url: str = "http://localhost:8080"
    tavily_api_key: str = ""

    # 메신저 커넥터
    telegram_bot_token: str = ""
    discord_bot_token: str = ""

    # 데이터 경로
    vector_db_path: str = "./data/vectordb"
    models_path: str = "./data/models"

    def get_model_config(self, role: AgentRole) -> ModelConfig:
        model_id_map = {
            AgentRole.ORCHESTRATOR: self.orchestrator_model,
            AgentRole.CODE: self.code_model,
            AgentRole.RAG: self.rag_model,
            AgentRole.JUDGE: self.judge_model,
            AgentRole.SEARCH: self.search_model,
            AgentRole.SUMMARY: self.summary_model,
        }
        # 오케스트레이터와 코드 에이전트는 더 많은 토큰 허용
        max_tokens = 8192 if role in (AgentRole.ORCHESTRATOR, AgentRole.CODE) else self.max_tokens
        temp = 0.3 if role == AgentRole.ORCHESTRATOR else self.temperature

        return ModelConfig(
            model_id=model_id_map[role],
            max_tokens=max_tokens,
            temperature=temp,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
