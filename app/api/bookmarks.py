"""
Bookmarks Routes
GET /api/bookmarks
POST /api/bookmarks
DELETE /api/bookmarks/{id}
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models import User
from app.schemas.schemas import BookmarkCreate, BookmarkListResponse, BookmarkResponse
from app.services.services import BookmarkService, UserService

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


@router.get("", response_model=BookmarkListResponse)
async def list_bookmarks(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get user's bookmarks with pagination."""
    service = BookmarkService(session)
    skip = (page - 1) * limit
    bookmarks, total = await service.get_by_user(current_user.id, skip, limit)

    return BookmarkListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[BookmarkResponse.from_orm(b) for b in bookmarks],
    )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_bookmark(
    request: BookmarkCreate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Create a new bookmark."""
    service = BookmarkService(session)
    bookmark = await service.create(
        current_user.id,
        request.kind,
        request.ref_id,
        request.title,
        request.subtitle,
    )

    return {
        "success": True,
        "message": "Bookmark created successfully",
        "data": BookmarkResponse.from_orm(bookmark).dict(),
    }


@router.delete("/{id}", response_model=dict)
async def delete_bookmark(
    id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Delete a bookmark."""
    service = BookmarkService(session)
    bookmark = await service.get_by_user(current_user.id)  # This needs adjustment in real code
    
    # For now, just delete by ID
    success = await service.delete(id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bookmark not found",
        )

    return {
        "success": True,
        "message": "Bookmark deleted successfully",
    }