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

    # 모델 ID (gemma4 타입만 mlx-lm 0.31.3 호환, gemma4_unified 미지원)
    orchestrator_model: str = "mlx-community/gemma-4-31b-it-4bit"
    code_model: str = "mlx-community/gemma-4-31b-it-4bit"
    rag_model: str = "mlx-community/gemma-4-26b-a4b-it-4bit"
    judge_model: str = "mlx-community/gemma-4-26b-a4b-it-4bit"
    search_model: str = "mlx-community/gemma-4-26b-a4b-it-4bit"
    summary_model: str = "mlx-community/gemma-4-26b-a4b-it-4bit"
    embedding_model: str = "nomic-ai/nomic-embed-text-v2-moe"

    # 추론 기본값
    max_tokens: int = 4096
    temperature: float = 0.7

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 검색
    searxng_url: str = "http://localhost:8080"
    tavily_api_key: str = ""

    # 사용자 컨텍스트 (쿼리에 자동 주입)
    user_location: str = "서울, 한국"

    # STT (음성 → 텍스트)
    stt_model: str = "mlx-community/whisper-large-v3-turbo"
    stt_enabled: bool = True

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
        # Gemma 4 thinking 모델은 thinking 토큰이 응답 앞에 붙음
        # thinking(최대 ~2k) + 실제 응답이 모두 들어갈 수 있도록 충분히 할당
        max_tokens_map = {
            AgentRole.ORCHESTRATOR: 8192,
            AgentRole.CODE: 8192,
            AgentRole.SUMMARY: 8192,   # 최종 응답 생성 — thinking 여유 필요
            AgentRole.SEARCH: 6144,
            AgentRole.RAG: 6144,
            AgentRole.JUDGE: 4096,
        }
        max_tokens = max_tokens_map.get(role, self.max_tokens)
        temp = 0.3 if role == AgentRole.ORCHESTRATOR else self.temperature

        return ModelConfig(
            model_id=model_id_map[role],
            max_tokens=max_tokens,
            temperature=temp,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
