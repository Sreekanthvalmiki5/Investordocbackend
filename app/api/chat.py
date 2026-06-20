"""
Chat Routes
POST /api/chat
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models import User
from app.schemas.schemas import ChatRequest, ChatResponse, MessageResponse
from app.services.services import ChatService, UserService

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


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """
    Process chat message and return AI response.
    
    - **message**: User's question/message
    - **company_id**: Optional company context
    - **model**: LLM model to use (gpt-4, claude-3, etc)
    - **conversation_id**: Optional - continue existing conversation
    
    Response includes:
    - The assistant's message with citations/sources
    - Conversation ID (new or existing)
    """
    try:
        service = ChatService(session)
        message = await service.chat(current_user.id, request)

        return ChatResponse(
            success=True,
            message="Chat message processed successfully",
            data=MessageResponse.from_orm(message),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}",
        )