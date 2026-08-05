"""
Transcription Service

Runs speech-to-text fully locally with Faster-Whisper (CTranslate2 + PyAV).
No OpenAI API key is required — the Whisper model is downloaded once from
Hugging Face on first use and then runs entirely on this machine.

Design notes:
  - The model is loaded exactly once per process (module-level singleton) and
    reused for every request. It is never reloaded per request.
  - Uploads are written to a temp file, transcribed, then deleted — even when
    transcription fails (the `finally` block guarantees cleanup).
  - Faster-Whisper models are not fully thread-safe for concurrent transcribe
    calls, so CPU-bound decoding is serialized with a lock. Concurrent requests
    queue up rather than corrupting state.
"""

import asyncio
import logging
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when audio cannot be transcribed (empty, corrupted, no speech)."""


@dataclass
class TranscriptionResult:
    """Outcome of a local transcription."""

    transcript: str
    language: Optional[str] = None
    duration: Optional[float] = None


class TranscriptionService:
    """Singleton that lazily loads a Faster-Whisper model and transcribes audio."""

    _instance: Optional["TranscriptionService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._model = None
        self._model_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "TranscriptionService":
        """Return the process-wide singleton (model loaded at most once)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _load_model(self):
        """Load the Faster-Whisper model once (idempotent, thread-safe)."""
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    model_size = (settings.WHISPER_MODEL or "small").strip()
                    logger.info(
                        "Loading Faster-Whisper model '%s' on %s (%s) — "
                        "first request downloads the weights from Hugging Face",
                        model_size,
                        settings.WHISPER_DEVICE,
                        settings.WHISPER_COMPUTE_TYPE,
                    )
                    started = time.perf_counter()
                    self._model = WhisperModel(
                        model_size,
                        device=settings.WHISPER_DEVICE,
                        compute_type=settings.WHISPER_COMPUTE_TYPE,
                    )
                    logger.info(
                        "Faster-Whisper model '%s' loaded in %.1fs",
                        model_size,
                        time.perf_counter() - started,
                    )
        return self._model

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        file_bytes: bytes,
        filename: str = "recording.webm",
        content_type: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes with the shared local model.

        Raises:
            TranscriptionError: for empty, corrupted, unsupported, or silent audio.
        """
        if not file_bytes:
            raise TranscriptionError("The audio file is empty. Please record again.")

        # Persist the upload to a temp file (Faster-Whisper decodes from disk).
        # The extension from the upload is preserved so the decoder can sniff
        # the container format (wav / mp3 / m4a / webm).
        suffix = Path(filename or "recording.webm").suffix or ".webm"
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)

            logger.info("Transcription started (size=%d bytes)", len(file_bytes))
            started = time.perf_counter()

            try:
                result = await asyncio.to_thread(self._transcribe_file, tmp_path)
            except TranscriptionError:
                raise
            except Exception as exc:
                logger.warning(
                    "Faster-Whisper could not decode %s: %s", tmp_path.name, exc
                )
                raise TranscriptionError(
                    "Could not decode the audio file. Please send a valid wav, "
                    "mp3, m4a, or webm recording."
                ) from exc

            elapsed = time.perf_counter() - started
            logger.info(
                "Transcription completed in %.2fs (language=%s, duration=%.2fs)",
                elapsed,
                result.language,
                result.duration or 0.0,
            )
            return result
        finally:
            # Cleanup even when transcription fails (temp file must not linger).
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:  # pragma: no cover - defensive
                    logger.debug("Could not remove temp file %s", tmp_path)

    def _transcribe_file(self, path: Path) -> TranscriptionResult:
        """Run the blocking model inference for one file (called in a thread)."""
        model = self._load_model()

        # Serialize CPU-bound decoding: faster-whisper models are not fully
        # thread-safe, and int8 CPU inference gains nothing from parallelism.
        with self._model_lock:
            segments, info = model.transcribe(
                str(path),
                language=None,  # auto-detect
                vad_filter=True,  # skip silence; surfaces "no speech" cleanly
            )
            text_parts = [segment.text for segment in segments]

        text = " ".join(text_parts).strip()
        if not text:
            raise TranscriptionError(
                "No speech detected in the audio. Please try again."
            )

        return TranscriptionResult(
            transcript=text,
            language=getattr(info, "language", None),
            duration=getattr(info, "duration", None),
        )
