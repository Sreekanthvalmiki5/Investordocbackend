"""
Authentication Routes
POST /api/auth/register
POST /api/auth/login
GET /api/auth/me
POST /api/auth/logout
"""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.user import User
from app.schemas.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest
)
from app.services.services import AuthService

router = APIRouter()


@router.post("/register", response_model=AuthResponse)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user."""
    try:
        service = AuthService(session)
        user = await service.register(request)
        token = "temporary_token"  # Will be generated properly

        return AuthResponse(
            success=True,
            message="User registered successfully",
            data=TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=1440,
                user=UserResponse.model_validate(user),
            ),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    """Login user and return access token."""
    try:
        service = AuthService(session)
        user, token = await service.login(request)
        

        return AuthResponse(
            success=True,
            message="Login successful",
            data=TokenResponse(
                access_token=token,
                token_type="bearer",
                expires_in=1440,
                user=UserResponse.model_validate(user),
            ),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.get("/me", response_model=dict)
async def get_current_user(
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Get current authenticated user."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    # Extract token from "Bearer <token>"
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    user_id = decode_token(token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    service = AuthService(session)
    user = await service.get_current_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {
        "success": True,
        "data": UserResponse.from_orm(user).dict(),
    }


@router.post("/logout")
async def logout():
    """Logout user (frontend should delete token)."""
    return {
        "success": True,
        "message": "Logout successful",
    }
@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    service = AuthService(session)

    await service.request_password_reset(request.email)

    return {
        "success": True,
        "message": "If an account exists, a password reset link has been sent."
    }
    
@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    service = AuthService(session)

    await service.reset_password(
        request.token,
        request.password,
    )

    return {
        "success": True,
        "message": "Password updated successfully."
    }