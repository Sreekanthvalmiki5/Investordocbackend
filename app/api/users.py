"""
Users Routes

Self-service endpoints:
  GET    /api/users/me   — Current user profile
  PUT    /api/users/me   — Update own profile
  PATCH  /api/users/me   — Partial update own profile

Admin-only endpoints (require role="admin"):
  GET    /api/users          — List all users
  GET    /api/users/{id}     — Get one user
  PATCH  /api/users/{id}    — Update any user
  DELETE /api/users/{id}    — Delete any user
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User
from app.schemas.schemas import AdminUserListResponse, AdminUserResponse, AdminUserUpdate, UserResponse, UserUpdate
from app.services.services import UserService

router = APIRouter()


# ============================================================================
# Authentication Dependencies
# ============================================================================


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


async def require_admin(
    current_user: User = Depends(get_current_user_from_header),
) -> User:
    """Require the current user to have admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# ============================================================================
# Self-service Endpoints
# ============================================================================


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


# ============================================================================
# Admin-only Endpoints
# ============================================================================


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    role: Optional[str] = Query(None, description="Filter by role (user, admin)"),
    plan: Optional[str] = Query(None, description="Filter by plan (free, pro)"),
    sort_by: str = Query("created_at", description="Sort column"),
    sort_order: str = Query("desc", description="Sort order (asc, desc)"),
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    List all users with pagination, search, and filters.

    Admin only. Returns camelCase field names for frontend compatibility.
    """
    service = UserService(session)
    return await service.list_users(
        page=page,
        limit=limit,
        search=search,
        role=role,
        plan=plan,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get a single user by ID.

    Admin only. Returns camelCase field names.
    """
    service = UserService(session)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {"success": True, "data": user.model_dump()}


@router.patch("/{user_id}", response_model=dict)
async def update_user(
    user_id: str,
    request: AdminUserUpdate,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Update a user's fields (first_name, last_name, role, plan).

    Admin only.
    """
    service = UserService(session)
    updated = await service.update_user(user_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {
        "success": True,
        "message": "User updated successfully",
        "data": UserResponse.model_validate(updated).model_dump(),
    }


@router.delete("/{user_id}", response_model=dict)
async def delete_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a user and all related data (conversations, messages, bookmarks).

    Admin only. Deletion cascades via the ORM cascade="all, delete-orphan"
    on User relationships.
    """
    service = UserService(session)
    deleted = await service.delete_user(user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {
        "success": True,
        "message": "User deleted successfully",
    }