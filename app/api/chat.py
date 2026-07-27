"""
Chat Routes
POST /api/chat

Uses the production RAG pipeline for AI-powered financial document analysis.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models import User
from app.schemas.schemas import ChatRequest, RAGChatResponse
from app.services.services import ChatService, UserService

logger = logging.getLogger(__name__)

router = APIRouter()


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