import logging

from harness import MemoryStore

from .base import BaseConnector, IncomingMessage

logger = logging.getLogger(__name__)

_MAX_MSG_LEN = 1900  # Discord 한도 2000보다 여유


class DiscordConnector(BaseConnector):
    def __init__(self, token: str, graph, memory_store: MemoryStore):
        super().__init__(graph, memory_store)
        self._token = token
        self._client = None

    def _build_client(self):
        try:
            import discord
            from discord.ext import commands
        except ImportError:
            raise RuntimeError("discord.py 패키지 필요: pip install discord.py")

        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents)

        @bot.event
        async def on_ready() -> None:
            logger.info(f"[discord] 로그인: {bot.user}")

        @bot.command(name="clear")
        async def cmd_clear(ctx) -> None:
            session_id = str(ctx.channel.id)
            self._memory_store.delete(session_id)
            await ctx.send("대화 히스토리를 초기화했습니다.")

        @bot.event
        async def on_message(message) -> None:
            if message.author.bot:
                return
            # !clear 등 커맨드 처리
            await bot.process_commands(message)
            if message.content.startswith("!"):
                return

            session_id = str(message.channel.id)
            user_id = str(message.author.id)

            async with message.channel.typing():
                incoming = IncomingMessage(
                    session_id=session_id,
                    user_id=user_id,
                    text=message.content,
                    platform="discord",
                )
                response = await self.process(incoming)

            chunks = self.split_text(response, _MAX_MSG_LEN)
            for chunk in chunks:
                await message.reply(chunk)

        return bot

    async def start(self) -> None:
        logger.info("[discord] 봇 시작")
        self._client = self._build_client()
        await self._client.start(self._token)

    async def stop(self) -> None:
        if self._client:
            logger.info("[discord] 봇 종료")
            await self._client.close()
