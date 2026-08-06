"""
Conversations Routes
GET /api/conversations
POST /api/conversations
GET /api/conversations/{id}
PATCH /api/conversations/{id}
DELETE /api/conversations/{id}
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models import User
from app.schemas.schemas import ConversationCreate, ConversationListResponse, ConversationResponse, ConversationUpdate
from app.services.services import ConversationService, UserService

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


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get user's conversations with pagination."""
    service = ConversationService(session)
    skip = (page - 1) * limit
    conversations, total = await service.get_by_user(current_user.id, skip, limit)

    return ConversationListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[ConversationResponse.from_orm(c) for c in conversations],
    )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Create a new conversation."""
    service = ConversationService(session)
    conversation = await service.create(current_user.id, request)

    return {
        "success": True,
        "message": "Conversation created successfully",
        "data": ConversationResponse.from_orm(conversation).dict(),
    }


@router.get("/{id}", response_model=dict)
async def get_conversation(
    id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get conversation by ID."""
    service = ConversationService(session)
    conversation = await service.get_by_id(id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Verify ownership
    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this conversation",
        )

    return {
        "success": True,
        "data": ConversationResponse.from_orm(conversation).dict(),
    }


@router.patch("/{id}", response_model=dict)
async def update_conversation(
    id: str,
    request: ConversationUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Update a conversation."""
    service = ConversationService(session)
    conversation = await service.get_by_id(id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this conversation",
        )

    updated = await service.update(id, request)

    return {
        "success": True,
        "message": "Conversation updated successfully",
        "data": ConversationResponse.from_orm(updated).dict(),
    }


@router.delete("/{id}", response_model=dict)
async def delete_conversation(
    id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Delete a conversation."""
    service = ConversationService(session)
    conversation = await service.get_by_id(id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this conversation",
        )

    await service.delete(id)

    return {
        "success": True,
        "message": "Conversation deleted successfully",
    }