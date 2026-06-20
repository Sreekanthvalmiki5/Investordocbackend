"""
Dependencies
Dependency injection for FastAPI including current user, pagination, etc.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models import User
from app.schemas import PaginationParams


async def get_current_user(
    token: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    Get current authenticated user from JWT token.
    
    Raises:
        HTTPException: If token is missing or invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    user_id = decode_token(token)
    if user_id is None:
        raise credentials_exception

    # Fetch user from database
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_pagination(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginationParams:
    """Get pagination parameters from query params."""
    return PaginationParams(page=page, limit=limit)