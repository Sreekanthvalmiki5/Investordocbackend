"""
Chat Routes
POST /api/chat
POST /api/chat/voice   (audio -> local Faster-Whisper -> RAG pipeline)
POST /api/chat/image   (image -> vision extraction -> RAG pipeline)

Uses the production RAG pipeline for AI-powered financial document analysis.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.security import decode_token
from app.models import User
from app.schemas.schemas import ChatRequest, RAGChatResponse
from app.services.media_service import (
    AUDIO_CONTENT_TYPES,
    AUDIO_EXTENSIONS,
    IMAGE_CONTENT_TYPES,
    IMAGE_EXTENSIONS,
    extract_image_content,
)
from app.services.transcription_service import (
    TranscriptionError,
    TranscriptionService,
)
from app.services.services import ChatService, UserService

logger = logging.getLogger(__name__)

router = APIRouter()


def _validate_media_upload(
    file: UploadFile,
    allowed_extensions: set,
    allowed_content_types: set,
    max_size_bytes: int,
    label: str,
) -> None:
    """
    Validate an uploaded file's extension, MIME type, and size.

    Rejects mismatched or missing formats instead of letting the model call
    fail later with a confusing error. Raises HTTPException on failure.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    ctype = (file.content_type or "").lower()

    if ext and ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported {label} format. Allowed: {', '.join(sorted(allowed_extensions))}.",
        )
    if ctype and ctype not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported {label} content type. Allowed: {', '.join(sorted(allowed_content_types))}.",
        )
    if not ext and not ctype:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Could not determine the {label} format. Please include a file extension.",
        )

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label.capitalize()} file too large. Maximum size is {max_mb} MB.",
        )


async def get_current_user_from_header(
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Get current user from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    user_id = decode_token(token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    service = UserService(session)
    user = await service.get_profile(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.post("/voice", response_model=RAGChatResponse, status_code=status.HTTP_201_CREATED)
async def chat_voice(
    file: UploadFile = File(...),
    company_id: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """
    Transcribe a voice recording (wav / mp3 / m4a / webm) locally with
    Faster-Whisper and run the transcript through the RAG pipeline. Returns the
    same shape as /api/chat.
    """
    _validate_media_upload(
        file,
        AUDIO_EXTENSIONS,
        AUDIO_CONTENT_TYPES,
        settings.MAX_AUDIO_UPLOAD_MB * 1024 * 1024,
        "audio",
    )

    file_bytes = await file.read()
    try:
        result = await TranscriptionService.get_instance().transcribe(
            file_bytes,
            filename=file.filename or "recording.webm",
            content_type=file.content_type,
        )
        transcript = result.transcript
    except TranscriptionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    try:
        service = ChatService(session)
        result = await service.chat(
            current_user.id,
            ChatRequest(
                message=transcript,
                company_id=company_id,
                model=model,
                conversation_id=conversation_id,
            ),
        )
        return result
    except Exception as exc:
        logger.exception("Error processing voice chat request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing voice query: {str(exc)}",
        )


@router.post("/image", response_model=RAGChatResponse, status_code=status.HTTP_201_CREATED)
async def chat_image(
    file: UploadFile = File(...),
    message: str = Form(..., min_length=1, max_length=5000),
    company_id: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    conversation_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """
    Extract tables / numbers / text from an uploaded image (png / jpg / jpeg /
    webp) with a vision model, then answer the question using both the image
    content and the retrieved document context.
    """
    _validate_media_upload(
        file,
        IMAGE_EXTENSIONS,
        IMAGE_CONTENT_TYPES,
        settings.MAX_IMAGE_UPLOAD_MB * 1024 * 1024,
        "image",
    )

    file_bytes = await file.read()
    try:
        image_content = await extract_image_content(
            file_bytes,
            filename=file.filename or "image.png",
            content_type=file.content_type,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    try:
        service = ChatService(session)
        result = await service.chat(
            current_user.id,
            ChatRequest(
                message=message,
                company_id=company_id,
                model=model,
                conversation_id=conversation_id,
            ),
            extra_context=image_content,
        )
        return result
    except Exception as exc:
        logger.exception("Error processing image chat request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing image query: {str(exc)}",
        )


@router.post("", response_model=RAGChatResponse, status_code=status.HTTP_201_CREATED)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """
    Process chat message using the RAG pipeline.

    Args:
        request.message: User's question about financial documents
        request.company_id: Optional company context for scoping search
        request.model: LLM model (default: openai/gpt-4o)
        request.conversation_id: Optional existing conversation to continue

    Returns:
        {
            "conversation_id": "...",
            "content": "...AI answer with markdown formatting and citations..."
        }
    """
    try:
        service = ChatService(session)
        result = await service.chat(current_user.id, request)

        return result

    except Exception as e:
        logger.exception("Error processing chat request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}",
        )