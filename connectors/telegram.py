import asyncio
import logging
import pathlib
import tempfile

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ChatAction
from aiogram.filters import Command

from harness import MemoryStore
from harness.stream_ctx import set_stream_queue, clear_stream_queue

from .base import BaseConnector, IncomingMessage

logger = logging.getLogger(__name__)

_MAX_MSG_LEN = 4000          # Telegram 실제 한도 4096보다 약간 여유
_EDIT_INTERVAL_CHARS = 150   # 스트리밍 편집 주기 (글자 수)


class TelegramConnector(BaseConnector):
    def __init__(self, token: str, graph, memory_store: MemoryStore, stt=None, vlm=None):
        super().__init__(graph, memory_store)
        self._bot = Bot(token=token)
        self._dp = Dispatcher()
        self._stt = stt   # STTManager | None
        self._vlm = vlm   # VLMManager | None
        self._setup_handlers()

    # ── 핸들러 등록 ───────────────────────────────────────────────────────────

    def _setup_handlers(self) -> None:
        dp = self._dp

        @dp.message(Command("start"))
        async def cmd_start(message: types.Message) -> None:
            await message.answer(
                "안녕하세요! LocalAI입니다.\n\n"
                "질문을 입력하면 답변해드립니다.\n"
                "/help — 도움말\n"
                "/clear — 대화 초기화"
            )

        @dp.message(Command("help"))
        async def cmd_help(message: types.Message) -> None:
            await message.answer(
                "사용 가능한 명령어:\n"
                "/start — 시작\n"
                "/clear — 대화 히스토리 초기화\n"
                "/help — 이 도움말\n\n"
                "PDF, TXT 파일을 전송하면 지식베이스에 추가됩니다."
            )

        @dp.message(Command("clear"))
        async def cmd_clear(message: types.Message) -> None:
            session_id = str(message.chat.id)
            self._memory_store.delete(session_id)
            await message.answer("대화 히스토리를 초기화했습니다.")

        @dp.message(lambda m: m.document is not None)
        async def handle_document(message: types.Message) -> None:
            await self._handle_file(message)

        @dp.message(lambda m: m.photo is not None)
        async def handle_photo(message: types.Message) -> None:
            await self._handle_photo(message)

        @dp.message(lambda m: m.voice is not None or m.audio is not None
                    or m.video_note is not None or m.video is not None)
        async def handle_voice(message: types.Message) -> None:
            await self._handle_voice(message)

        @dp.message(lambda m: m.text and not m.text.startswith("/"))
        async def handle_text(message: types.Message) -> None:
            await self._handle_text(message)

    # ── 텍스트 처리 ───────────────────────────────────────────────────────────

    async def _handle_text(self, message: types.Message) -> None:
        session_id = str(message.chat.id)
        user_id = str(message.from_user.id)

        try:
            await self._bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:
            pass

        try:
            placeholder = await message.answer("생각 중... ⏳")
        except Exception:
            placeholder = None

        incoming = IncomingMessage(
            session_id=session_id,
            user_id=user_id,
            text=message.text,
            platform="telegram",
        )

        # 스트림 큐 생성 — synthesize 노드가 이 큐에 토큰을 실시간으로 씀
        stream_q: asyncio.Queue[str | None] = asyncio.Queue()
        set_stream_queue(stream_q)

        # 그래프를 백그라운드 태스크로 실행 (asyncio.create_task은 현재 컨텍스트 복사)
        typing_task = asyncio.create_task(self._keep_typing(message.chat.id))
        graph_task = asyncio.create_task(self._run_with_error_handling(incoming))

        # synthesize 토큰 스트리밍 → Telegram 실시간 편집
        accumulated = ""
        last_edit_len = 0
        first_chunk = True
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(stream_q.get(), timeout=90.0)
                except asyncio.TimeoutError:
                    logger.warning("[telegram] 스트림 타임아웃 — 그래프 완료 대기")
                    break
                if chunk is None:  # sentinel — synthesize 완료
                    break
                if first_chunk:
                    typing_task.cancel()  # 첫 토큰 도착 시 타이핑 인디케이터 즉시 해제
                    first_chunk = False
                accumulated += chunk
                # Telegram API rate limit 고려 — 200자마다 편집
                if len(accumulated) - last_edit_len >= 200 and placeholder:
                    try:
                        await placeholder.edit_text(accumulated + " ▌")
                        last_edit_len = len(accumulated)
                    except Exception:
                        pass
        finally:
            typing_task.cancel()

        # 그래프 완료 대기 (judge가 있는 rag 라우트 등)
        try:
            response = await graph_task
        except Exception as e:
            logger.error(f"[telegram] 처리 오류: {e}")
            response = accumulated or "처리 중 오류가 발생했습니다."

        clear_stream_queue()

        # 최종 응답 전송 (judge retry로 응답이 달라질 수 있으므로 graph 결과 우선)
        final = response or accumulated or "응답을 생성하지 못했습니다."
        chunks = self.split_text(str(final), _MAX_MSG_LEN)
        try:
            if placeholder:
                await placeholder.edit_text(chunks[0])
            else:
                await message.answer(chunks[0])
            for chunk in chunks[1:]:
                await message.answer(chunk)
        except Exception as e:
            logger.error(f"[telegram] 응답 전송 실패: {e}")

    async def _run_with_error_handling(self, incoming: IncomingMessage) -> str:
        """그래프 실행 래퍼 — 예외를 잡아 에러 메시지 반환."""
        try:
            return await self.process(incoming)
        except Exception as e:
            logger.error(f"[telegram] 그래프 실행 오류: {e}")
            return "처리 중 오류가 발생했습니다."

    # ── 음성 처리 (STT) ───────────────────────────────────────────────────────

    async def _handle_voice(self, message: types.Message) -> None:
        if not self._stt:
            await message.answer("음성 인식이 비활성화되어 있습니다.")
            return

        media = message.voice or message.audio or message.video_note or message.video
        is_video = message.video_note is not None or message.video is not None

        try:
            status = await message.answer("🎙 음성 인식 중...")
        except Exception:
            status = None

        try:
            await self._bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        except Exception:
            pass

        try:
            # 음성/영상 파일 다운로드
            file = await self._bot.get_file(media.file_id)
            suffix = pathlib.Path(file.file_path).suffix or (".mp4" if is_video else ".ogg")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                await self._bot.download_file(file.file_path, tmp)
                tmp_path = tmp.name

            # 영상 파일이면 ffmpeg으로 오디오 추출 후 STT
            if is_video:
                wav_path = tmp_path.replace(suffix, ".wav")
                import subprocess as _sp
                try:
                    _sp.run(
                        ["ffmpeg", "-y", "-i", tmp_path, "-vn",
                         "-acodec", "pcm_s16le", "-ar", "16000", wav_path],
                        capture_output=True, check=True, timeout=30,
                    )
                    pathlib.Path(tmp_path).unlink(missing_ok=True)
                    tmp_path = wav_path
                except Exception as e:
                    logger.warning(f"[telegram] 영상 오디오 추출 실패, 원본 시도: {e}")

            # STT 변환 (thread executor — 동기 함수)
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(
                None, self._stt.transcribe, tmp_path
            )
            pathlib.Path(tmp_path).unlink(missing_ok=True)

            if not text:
                if status:
                    try:
                        await status.edit_text("음성을 인식하지 못했습니다. 다시 시도해주세요.")
                    except Exception:
                        pass
                return

            if status:
                try:
                    await status.edit_text(f'🎙 "{text}"')
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[telegram] 음성 처리 오류: {e}")
            if status:
                try:
                    await status.edit_text("음성 처리 중 오류가 발생했습니다.")
                except Exception:
                    pass
            return

        # 인식된 텍스트를 텍스트 핸들러와 동일하게 스트리밍 처리
        try:
            placeholder = await message.answer("생각 중... ⏳")
        except Exception:
            placeholder = None

        incoming = IncomingMessage(
            session_id=str(message.chat.id),
            user_id=str(message.from_user.id),
            text=text,
            platform="telegram",
        )

        stream_q: asyncio.Queue[str | None] = asyncio.Queue()
        set_stream_queue(stream_q)

        typing_task = asyncio.create_task(self._keep_typing(message.chat.id))
        graph_task = asyncio.create_task(self._run_with_error_handling(incoming))

        accumulated = ""
        last_edit_len = 0
        first_chunk = True
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(stream_q.get(), timeout=90.0)
                except asyncio.TimeoutError:
                    logger.warning("[telegram] 음성 스트림 타임아웃")
                    break
                if chunk is None:
                    break
                if first_chunk:
                    typing_task.cancel()
                    first_chunk = False
                accumulated += chunk
                if len(accumulated) - last_edit_len >= 200 and placeholder:
                    try:
                        await placeholder.edit_text(accumulated + " ▌")
                        last_edit_len = len(accumulated)
                    except Exception:
                        pass
        finally:
            typing_task.cancel()

        try:
            response = await graph_task
        except Exception as e:
            logger.error(f"[telegram] 음성 쿼리 처리 오류: {e}")
            response = accumulated or "처리 중 오류가 발생했습니다."

        clear_stream_queue()

        final = response or accumulated or "응답을 생성하지 못했습니다."
        chunks = self.split_text(str(final), _MAX_MSG_LEN)
        try:
            if placeholder:
                await placeholder.edit_text(chunks[0])
            else:
                await message.answer(chunks[0])
            for chunk in chunks[1:]:
                await message.answer(chunk)
        except Exception as e:
            logger.error(f"[telegram] 음성 응답 전송 실패: {e}")

    # ── 이미지 처리 (VLM) ────────────────────────────────────────────────────────

    async def _handle_photo(self, message: types.Message) -> None:
        if not self._vlm:
            await message.answer("이미지 분석이 비활성화되어 있습니다.")
            return

        question = message.caption or "이 이미지를 자세히 설명해줘"

        try:
            status = await message.answer("🖼 이미지 분석 중...")
        except Exception:
            status = None

        try:
            photo = message.photo[-1]  # largest size
            file = await self._bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                await self._bot.download_file(file.file_path, tmp)
                tmp_path = tmp.name

            response = await self._vlm.analyze(tmp_path, question)
            pathlib.Path(tmp_path).unlink(missing_ok=True)

            chunks = self.split_text(response, _MAX_MSG_LEN)
            if status:
                await status.edit_text(chunks[0])
            else:
                await message.answer(chunks[0])
            for chunk in chunks[1:]:
                await message.answer(chunk)
        except Exception as e:
            logger.error(f"[telegram] 이미지 처리 오류: {e}")
            if status:
                try:
                    await status.edit_text("이미지 처리 중 오류가 발생했습니다.")
                except Exception:
                    pass

    # ── 파일 처리 (RAG 인덱싱) ─────────────────────────────────────────────────

    async def _handle_file(self, message: types.Message) -> None:
        doc = message.document
        allowed = {".pdf", ".txt", ".md"}
        import pathlib
        suffix = pathlib.Path(doc.file_name).suffix.lower()

        if suffix not in allowed:
            await message.answer(f"지원하지 않는 파일 형식입니다. ({', '.join(allowed)})")
            return

        status = await message.answer(f"📄 {doc.file_name} 처리 중...")

        try:
            import tempfile, pathlib
            file = await self._bot.get_file(doc.file_id)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                await self._bot.download_file(file.file_path, tmp)
                tmp_path = tmp.name

            # app.state의 indexer에 접근하기 위해 graph에서 참조 (runner가 주입)
            if self._indexer:
                count = await asyncio.get_event_loop().run_in_executor(
                    None, self._indexer.index_file, tmp_path
                )
                await status.edit_text(f"✅ {doc.file_name} — {count}개 청크 인덱싱 완료")
            else:
                await status.edit_text("인덱서가 연결되지 않았습니다.")

            pathlib.Path(tmp_path).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"[telegram] 파일 처리 오류: {e}")
            await status.edit_text(f"파일 처리 중 오류가 발생했습니다: {e}")

    # ── 유틸 ──────────────────────────────────────────────────────────────────

    async def _keep_typing(self, chat_id: int, interval: float = 4.0) -> None:
        """그래프 실행 중 타이핑 인디케이터 유지 (Telegram은 5초마다 갱신 필요)."""
        try:
            for _ in range(20):  # 최대 80초
                await asyncio.sleep(interval)
                try:
                    await self._bot.send_chat_action(chat_id, ChatAction.TYPING)
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    def set_indexer(self, indexer) -> None:
        """파일 인덱싱용 Indexer 주입 (runner에서 호출)."""
        self._indexer = indexer

    # ── 시작 / 종료 ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        logger.info("[telegram] 봇 시작 (polling)")
        self._indexer = None
        await self._dp.start_polling(self._bot, handle_signals=False)

    async def stop(self) -> None:
        logger.info("[telegram] 봇 종료")
        await self._dp.stop_polling()
        await self._bot.session.close()
