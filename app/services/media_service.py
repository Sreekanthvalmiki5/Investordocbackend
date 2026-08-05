"""
Media Service

Voice queries:
  - Accepts wav / mp3 / m4a / webm audio
  - Transcribed locally with Faster-Whisper (see transcription_service.py)

Image analysis:
  - Accepts png / jpg / jpeg / webp images
  - Extracts tables, numbers, and text with a vision-capable LLM
    (OpenRouter by default, falling back to OpenAI; both support image_url
    content parts)

The transcribed text / extracted content is fed into the existing RAG pipeline,
so answers combine image context with the retrieved document context.
"""

import asyncio
import base64
import logging
from typing import List, Optional

from app.core.config import is_openrouter_key, settings

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "webm"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

AUDIO_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "audio/webm",
    "video/webm",
    # Some browsers/recorders omit the MIME type for recorded audio.
    "application/octet-stream",
}
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}

VISION_SYSTEM_PROMPT = (
    "You are a financial document OCR assistant. Extract ALL text, tables, "
    "numbers, chart values, and financial figures from the attached image. "
    "Preserve structure: list tables with rows and columns, note units "
    "(e.g., Rs crore, $M, %), and include headings. If the image is a chart "
    "or graph, describe the values, trends, and axis labels. "
    "Output plain text only."
)


def _get_vision_client():
    """Vision-capable chat client — prefers OpenRouter (existing key), falls back to OpenAI."""
    from openai import OpenAI

    router_key = (settings.OPENROUTER_API_KEY or "").strip()
    api_key = (settings.OPENAI_API_KEY or "").strip()

    if router_key:
        return OpenAI(
            api_key=router_key,
            base_url=settings.OPENROUTER_API_BASE,
        )
    if api_key and not is_openrouter_key(api_key):
        return OpenAI(api_key=api_key)
    if api_key:
        # Only an OpenRouter key is configured (in OPENAI_API_KEY) — route it
        # to OpenRouter instead of letting OpenAI reject it with a 401.
        return OpenAI(
            api_key=api_key,
            base_url=settings.OPENROUTER_API_BASE,
        )
    return None


# ---------------------------------------------------------------------------
# Image content extraction
# ---------------------------------------------------------------------------


async def extract_image_content(
    file_bytes: bytes,
    filename: str = "image.png",
    content_type: Optional[str] = None,
) -> str:
    """Extract text / tables / numbers from an image using a vision LLM."""
    client = _get_vision_client()
    if client is None:
        raise RuntimeError(
            "Image analysis requires an OPENROUTER_API_KEY or OPENAI_API_KEY."
        )

    b64 = base64.b64encode(file_bytes).decode("ascii")
    ext = (filename or "image.png").rsplit(".", 1)[-1].lower() or "png"
    if ext == "jpg":
        ext = "jpeg"
    data_uri = f"data:image/{ext};base64,{b64}"

    # Model names differ between OpenAI's direct API (gpt-4o-mini) and
    # OpenRouter (openai/gpt-4o-mini). Build the candidate list for whichever
    # client is actually configured.
    if settings.OPENROUTER_API_KEY:
        models: List[str] = [
            settings.VISION_MODEL,
            "google/gemini-2.0-flash",
            "openai/gpt-4o",
        ]
    else:
        models = ["gpt-4o-mini", "gpt-4o"]

    user_content: List[dict] = [
        {"type": "text", "text": "Extract the complete contents of this image."},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]

    last_error: Optional[Exception] = None
    for model in models:
        try:
            response = await asyncio.to_thread(
                lambda m=model: client.chat.completions.create(
                    model=m,
                    temperature=0.0,
                    max_tokens=2048,
                    messages=[
                        {"role": "system", "content": VISION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                )
            )
            content = (response.choices[0].message.content or "").strip()
            if content:
                return content
        except Exception as exc:  # model may not support vision / rate-limited
            last_error = exc
            logger.warning("Vision model %s failed: %s", model, exc)
            continue

    raise RuntimeError(
        f"Image analysis failed. Please try again. ({last_error})"
        if last_error
        else "Image analysis failed. Please try again."
    )
