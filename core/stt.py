"""
Speech-to-Text — mlx-whisper 기반 로컬 STT.
음성 파일(ogg/m4a/mp3/wav 등)을 텍스트로 변환.
"""
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# large-v3-turbo: 속도·품질 최적 균형, 한국어 지원
_DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


class STTManager:
    """mlx-whisper 래퍼. 앱 시작 시 한 번 로드, 이후 재사용."""

    def __init__(self, model_id: str = _DEFAULT_MODEL):
        self._model_id = model_id
        self._model = None
        self._processor = None

    def load(self) -> None:
        import mlx_whisper
        import numpy as np
        logger.info(f"[stt] 모델 로드 중: {self._model_id}")
        # 1초짜리 무음 배열로 warmup — 파일 없이도 모델 가중치 메모리 적재
        silence = np.zeros(16000, dtype=np.float32)
        try:
            mlx_whisper.transcribe(silence, path_or_hf_id=self._model_id)
        except Exception:
            pass  # 무음 처리 실패해도 모델은 로드됨
        logger.info("[stt] STT 모델 준비 완료")

    def transcribe(self, audio_path: str | Path) -> str:
        """
        음성 파일 → 텍스트 변환.
        ogg(Telegram 음성)는 ffmpeg으로 wav 변환 후 처리.
        """
        import mlx_whisper

        audio_path = Path(audio_path)
        work_path = audio_path

        # ogg/oga는 ffmpeg으로 wav 변환 (mlx-whisper가 직접 못 읽는 경우 대비)
        if audio_path.suffix.lower() in (".ogg", ".oga"):
            wav = Path(tempfile.mktemp(suffix=".wav"))
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(audio_path), str(wav)],
                    capture_output=True, check=True, timeout=30,
                )
                work_path = wav
            except (subprocess.CalledProcessError, FileNotFoundError):
                # ffmpeg 없으면 원본으로 시도
                logger.warning("[stt] ffmpeg 미설치 — ogg 원본으로 시도")

        try:
            result = mlx_whisper.transcribe(
                str(work_path),
                path_or_hf_id=self._model_id,
                language="ko",       # 한국어 우선, 자동감지도 잘 됨
                word_timestamps=False,
            )
            text = result.get("text", "").strip()
            logger.info(f"[stt] 변환 완료: {text[:80]}")
            return text
        except Exception as e:
            logger.error(f"[stt] 변환 실패: {e}")
            return ""
        finally:
            if work_path != audio_path and work_path.exists():
                work_path.unlink(missing_ok=True)
