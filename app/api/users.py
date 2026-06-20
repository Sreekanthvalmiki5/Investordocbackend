"""
Users Routes
GET /api/users/me
PUT /api/users/me
PATCH /api/users/me
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User
from app.schemas.schemas import UserResponse, UserUpdate
from app.services.services import UserService

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


@router.get("/me", response_model=dict)
async def get_profile(
    current_user: User = Depends(get_current_user_from_header),
):
    """Get current user profile."""
    return {
        "success": True,
        "data": UserResponse.from_orm(current_user).dict(),
    }


@router.put("/me", response_model=dict)
async def update_profile(
    request: UserUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Update user profile."""
    service = UserService(session)
    updated_user = await service.update_profile(current_user.id, request)

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update profile",
        )

    return {
        "success": True,
        "message": "Profile updated successfully",
        "data": UserResponse.from_orm(updated_user).dict(),
    }


@router.patch("/me", response_model=dict)
async def patch_profile(
    request: UserUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Partially update user profile."""
    service = UserService(session)
    updated_user = await service.update_profile(current_user.id, request)

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update profile",
        )

    return {
        "success": True,
        "message": "Profile updated successfully",
        "data": UserResponse.from_orm(updated_user).dict(),
    }