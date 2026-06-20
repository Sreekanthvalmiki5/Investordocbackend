"""
Messages Routes
GET /api/conversations/{id}/messages
POST /api/messages
DELETE /api/messages/{id}
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User
from app.schemas.schemas import MessageCreate, MessageListResponse, MessageResponse
from app.services.services import ConversationService, MessageService, UserService

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


@router.get("/{id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get all messages in a conversation."""
    conv_service = ConversationService(session)
    conversation = await conv_service.get_by_id(id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this conversation",
        )

    msg_service = MessageService(session)
    messages = await msg_service.get_by_conversation(id)

    return MessageListResponse(
        success=True,
        items=[MessageResponse.from_orm(m) for m in messages],
    )


@router.post("/{id}/messages", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_message(
    id: str,
    request: MessageCreate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Create a new message in a conversation."""
    conv_service = ConversationService(session)
    conversation = await conv_service.get_by_id(id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this conversation",
        )

    msg_service = MessageService(session)
    message = await msg_service.create(id, request)

    return {
        "success": True,
        "message": "Message created successfully",
        "data": MessageResponse.from_orm(message).dict(),
    }


@router.delete("/{msg_id}", response_model=dict)
async def delete_message(
    msg_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Delete a message."""
    msg_service = MessageService(session)
    message = await msg_service.get_by_id(msg_id)

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    # Verify user owns the conversation
    conv_service = ConversationService(session)
    conversation = await conv_service.get_by_id(message.conversation_id)

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this message",
        )

    await msg_service.delete(msg_id)

    return {
        "success": True,
        "message": "Message deleted successfully",
    }