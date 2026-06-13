import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from mlx_lm import generate, load, stream_generate
from mlx_lm.sample_utils import make_sampler

from .config import AgentRole, ModelConfig, Settings

logger = logging.getLogger(__name__)

import re

def _strip_thinking(text: str) -> str:
    """Gemma 4 thinking 채널 태그 제거."""
    # 완전한 블록: <|channel>thought ... <channel|> 제거
    text = re.sub(r"<\|channel>thought.*?<channel\|>", "", text, flags=re.DOTALL)
    # 닫힘 태그 없이 끝난 경우: <|channel>thought 이후 전부 제거
    text = re.sub(r"<\|channel>thought.*", "", text, flags=re.DOTALL)
    return text.strip()


class ModelInstance:
    """단일 MLX 모델 인스턴스 — generate/stream 비동기 래핑."""

    def __init__(
        self,
        role: AgentRole,
        model,
        tokenizer,
        config: ModelConfig,
        executor: ThreadPoolExecutor,
    ):
        self.role = role
        self.config = config
        self._model = model
        self._tokenizer = tokenizer
        # MLX GPU 스트림은 thread-local — 모델당 단일 전용 스레드 공유
        self._executor = executor
        self._lock = asyncio.Lock()

    def _build_prompt(self, messages: list[dict]) -> str:
        if hasattr(self._tokenizer, "apply_chat_template"):
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"

    async def generate(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        prompt = self._build_prompt(messages)
        temp = temperature if temperature is not None else self.config.temperature
        kwargs = {
            "max_tokens": max_tokens or self.config.max_tokens,
            "sampler": make_sampler(temp=temp),
        }
        async with self._lock:
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                self._executor,
                lambda: generate(self._model, self._tokenizer, prompt=prompt, **kwargs),
            )
            return _strip_thinking(raw)

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        prompt = self._build_prompt(messages)
        temp = temperature if temperature is not None else self.config.temperature
        kwargs = {
            "max_tokens": max_tokens or self.config.max_tokens,
            "sampler": make_sampler(temp=temp),
        }

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _producer():
            try:
                for response in stream_generate(
                    self._model, self._tokenizer, prompt=prompt, **kwargs
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, response.text)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        async with self._lock:
            self._executor.submit(_producer)
            # thinking 블록을 버퍼에 수집, <channel|> 이후만 스트리밍
            buffer = ""
            thinking_done = False
            while True:
                chunk = await queue.get()
                if chunk is None:
                    if not thinking_done:
                        # 닫힘 태그 없이 끝난 경우 — thinking만 있고 실제 응답 없음
                        cleaned = _strip_thinking(buffer)
                        if cleaned:
                            yield cleaned
                    break
                if not thinking_done:
                    buffer += chunk
                    marker = "<channel|>"
                    idx = buffer.find(marker)
                    if idx != -1:
                        thinking_done = True
                        after = buffer[idx + len(marker):].strip()
                        if after:
                            yield after
                else:
                    yield chunk


class ModelManager:
    """
    전체 에이전트 모델을 관리하는 싱글턴.
    M5 Pro 128GB 기준 모든 모델을 동시에 메모리에 올림.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._instances: dict[AgentRole, ModelInstance] = {}

    async def load_all(self) -> None:
        """
        앱 시작 시 모든 에이전트 모델을 병렬 로드.
        동일 model_id를 쓰는 role은 같은 (model, tokenizer, executor)를 공유.
        MLX GPU 스트림이 thread-local이므로 model_id당 하나의 전용 스레드를 유지.
        """
        roles = list(AgentRole)
        logger.info(f"모델 {len(roles)}개 로드 시작 (중복 ID 공유)...")

        loop = asyncio.get_event_loop()

        # model_id → (model, tokenizer, executor) 캐시
        _loaded: dict[str, tuple] = {}
        _locks: dict[str, asyncio.Lock] = {}

        async def _load_one(role: AgentRole) -> None:
            config = self._settings.get_model_config(role)
            mid = config.model_id

            if mid not in _locks:
                _locks[mid] = asyncio.Lock()
            async with _locks[mid]:
                if mid not in _loaded:
                    logger.info(f"[{role.value}] 로드 중: {mid}")
                    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"mlx-{mid[:20]}")
                    # 모델 로드도 전용 스레드에서 — GPU 스트림 초기화
                    model, tokenizer = await loop.run_in_executor(executor, load, mid)
                    _loaded[mid] = (model, tokenizer, executor)
                    logger.info(f"[{role.value}] 로드 완료")
                else:
                    logger.info(f"[{role.value}] 공유 사용: {mid}")

            model, tokenizer, executor = _loaded[mid]
            self._instances[role] = ModelInstance(role, model, tokenizer, config, executor)

        await asyncio.gather(*[_load_one(role) for role in roles])
        unique = len({self._settings.get_model_config(r).model_id for r in roles})
        logger.info(f"전체 모델 로드 완료 (role={len(roles)}, 고유모델={unique})")

    async def load(self, role: AgentRole) -> None:
        """단일 모델만 로드 (개발/테스트용)."""
        config = self._settings.get_model_config(role)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"mlx-{role.value}")
        loop = asyncio.get_event_loop()
        model, tokenizer = await loop.run_in_executor(executor, load, config.model_id)
        self._instances[role] = ModelInstance(role, model, tokenizer, config, executor)

    def get(self, role: AgentRole) -> ModelInstance:
        if role not in self._instances:
            raise RuntimeError(
                f"모델 미로드: {role.value} — load_all() 또는 load({role.value}) 먼저 호출 필요"
            )
        return self._instances[role]

    @property
    def loaded_roles(self) -> list[AgentRole]:
        return list(self._instances.keys())
