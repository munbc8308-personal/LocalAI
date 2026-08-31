import asyncio
import logging

from core.config import Settings
from harness import MemoryStore

from .base import BaseConnector
from .discord import DiscordConnector
from .telegram import TelegramConnector

logger = logging.getLogger(__name__)


class ConnectorRunner:
    """
    활성화된 커넥터를 asyncio 태스크로 실행/관리.
    FastAPI lifespan에서 백그라운드 태스크로 시작.
    """

    def __init__(self, settings: Settings, graph, memory_store: MemoryStore, indexer=None, stt=None, vlm=None):
        self._settings = settings
        self._graph = graph
        self._memory_store = memory_store
        self._indexer = indexer
        self._stt = stt
        self._vlm = vlm
        self._connectors: list[BaseConnector] = []
        self._tasks: list[asyncio.Task] = []

    def _build_connectors(self) -> list[BaseConnector]:
        connectors = []

        if self._settings.telegram_bot_token:
            tg = TelegramConnector(
                token=self._settings.telegram_bot_token,
                graph=self._graph,
                memory_store=self._memory_store,
                stt=self._stt,
                vlm=self._vlm,
            )
            tg.set_indexer(self._indexer)
            connectors.append(tg)
            logger.info("[runner] Telegram 커넥터 등록")
        else:
            logger.info("[runner] TELEGRAM_BOT_TOKEN 미설정 — Telegram 봇 비활성화")

        if self._settings.discord_bot_token:
            dc = DiscordConnector(
                token=self._settings.discord_bot_token,
                graph=self._graph,
                memory_store=self._memory_store,
            )
            connectors.append(dc)
            logger.info("[runner] Discord 커넥터 등록")
        else:
            logger.info("[runner] DISCORD_BOT_TOKEN 미설정 — Discord 봇 비활성화")

        return connectors

    async def start(self) -> None:
        self._connectors = self._build_connectors()
        if not self._connectors:
            logger.info("[runner] 활성 커넥터 없음")
            return

        for connector in self._connectors:
            task = asyncio.create_task(
                self._run_connector(connector),
                name=type(connector).__name__,
            )
            self._tasks.append(task)

        logger.info(f"[runner] {len(self._connectors)}개 커넥터 시작")

    async def stop(self) -> None:
        for connector in self._connectors:
            try:
                await connector.stop()
            except Exception as e:
                logger.warning(f"[runner] 커넥터 종료 오류: {e}")

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        self._tasks.clear()
        self._connectors.clear()
        logger.info("[runner] 모든 커넥터 종료")

    @staticmethod
    async def _run_connector(connector: BaseConnector) -> None:
        name = type(connector).__name__
        try:
            await connector.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[runner] {name} 오류: {e}", exc_info=True)
