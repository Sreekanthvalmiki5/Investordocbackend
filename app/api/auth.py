"""
Authentication Routes
POST /api/auth/register
POST /api/auth/login
POST /api/auth/google          (Google Identity Services ID-token flow)
GET  /api/auth/google/login    (server-side redirect flow — start)
GET  /api/auth/google/callback (server-side redirect flow — callback)
POST /api/auth/verify-email
POST /api/auth/resend-verification
GET /api/auth/me
POST /api/auth/logout
POST /api/auth/change-password   (signed-in user changes their password)
"""

import hashlib
import hmac
import secrets
import time
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.request_utils import get_client_ip
from app.core.security import decode_token, create_access_token
from app.models.user import User
from app.schemas.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    GoogleLoginRequest,
    VerifyEmailRequest,
    ResendVerificationRequest,
)
from app.services.google_auth import build_google_auth_url, exchange_google_code
from app.services.services import AuthService

router = APIRouter()

# Stateless, HMAC-signed OAuth `state` values for the server-side redirect
# flow. Self-verifiable (works across multiple uvicorn workers), time-limited,
# and protects the authorization-code exchange against CSRF.
_OAUTH_STATE_TTL_SECONDS = 600


def _sign_state(payload: str) -> str:
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def _issue_oauth_state() -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(16)}"
    return f"{payload}.{_sign_state(payload)}"


def _consume_oauth_state(state: str) -> bool:
    try:
        ts_str, _, signature = state.split(".", 2)
        payload = state.rsplit(".", 1)[0]
        if not hmac.compare_digest(_sign_state(payload), signature):
            return False
        return int(time.time()) - int(ts_str) <= _OAUTH_STATE_TTL_SECONDS
    except (ValueError, TypeError):
        return False


@router.post("/register", response_model=AuthResponse)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user."""
    try:
        service = AuthService(session)
        user = await service.register(request)
        # Email/password accounts must verify their address before they can
        # sign in — do not hand them a valid JWT until email_verified is True.
        token = create_access_token(user.id) if user.email_verified else ""

        return AuthResponse(
            success=True,
            message=(
                "User registered successfully. Please verify your email address."
                if not user.email_verified
                else "User registered successfully"
            ),
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
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Login user and return access token."""
    try:
        service = AuthService(session)
        user, token = await service.login(
            request,
            ip=get_client_ip(http_request),
            user_agent=http_request.headers.get("user-agent"),
        )

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


# ============================================================================
# Google OAuth
# ============================================================================


@router.post("/google", response_model=AuthResponse)
async def google_login(
    request: GoogleLoginRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Google sign-in via Google Identity Services ID token.

    The frontend obtains a credential from the Google popup flow and sends it
    here. The token is verified against GOOGLE_CLIENT_ID, the user is created
    if needed, and a standard InvestorDocs JWT is returned.
    """
    try:
        service = AuthService(session)
        user, token = await service.login_with_google(
            request.id_token,
            ip=get_client_ip(http_request),
            user_agent=http_request.headers.get("user-agent"),
        )

        return AuthResponse(
            success=True,
            message="Google sign-in successful",
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


@router.get("/google/login")
async def google_redirect_start():
    """Start the server-side Google OAuth redirect flow (fallback for the SPA)."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on the server.",
        )
    return RedirectResponse(build_google_auth_url(_issue_oauth_state()))


@router.get("/google/callback")
async def google_redirect_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Handle the Google OAuth callback: exchange the code, create-or-login the
    user, then redirect the browser back to the frontend with a JWT.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google sign-in failed: {error}",
        )
    if not code or not _consume_oauth_state(state or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google sign-in request.",
        )

    info = await exchange_google_code(code)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google sign-in failed. Please try again.",
        )

    try:
        service = AuthService(session)
        user, token = await service.login_with_google_redirect(
            info,
            ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    # Redirect back to the SPA; the frontend exchanges this JWT for the profile.
    redirect_url = f"{settings.FRONTEND_URL}/#/google-callback?token={token}"
    return RedirectResponse(redirect_url)


# ============================================================================
# Email verification
# ============================================================================


@router.post("/verify-email")
async def verify_email(
    request: VerifyEmailRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify a user's email address with the token from the emailed link."""
    service = AuthService(session)
    try:
        await service.verify_email(request.token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return {
        "success": True,
        "message": "Email verified successfully. You can now sign in.",
    }


@router.post("/resend-verification")
async def resend_verification(
    request: ResendVerificationRequest,
    session: AsyncSession = Depends(get_session),
):
    """Resend the verification email (never reveals whether an account exists)."""
    service = AuthService(session)
    await service.resend_verification(request.email)
    return {
        "success": True,
        "message": "If your account exists and is unverified, a new verification email has been sent.",
    }


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


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Change the signed-in user's password.

    Requires the current password; used from the profile page. (This is
    distinct from /reset-password, which uses an emailed reset token.)
    """
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

    service = AuthService(session)
    user = await service.get_current_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    try:
        await service.change_password(
            user.id,
            request.current_password,
            request.new_password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return {
        "success": True,
        "message": "Password updated successfully.",
    }