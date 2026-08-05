"""
Google OAuth helpers.

Supports two flows:
  1. ID-token verification (Google Identity Services popup flow on the SPA).
  2. Server-side redirect flow (authorize URL builder + authorization-code exchange).

ID tokens are verified using the official `google-auth` library, which validates
the signature against Google's JWKS and checks the audience (our client ID).
"""

import logging
from typing import Dict, Optional
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
ALLOWED_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_id_token(token: str) -> Optional[Dict[str, object]]:
    """
    Verify a Google ID token and return its decoded claims.

    Returns None when the token is invalid, expired, or was issued for a
    different audience (client ID) than the one we configured.
    """
    if not settings.GOOGLE_CLIENT_ID:
        logger.error("GOOGLE_CLIENT_ID is not configured")
        return None

    try:
        info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        logger.warning("Google ID token verification failed: %s", exc)
        return None

    if info.get("iss") not in ALLOWED_ISSUERS:
        logger.warning("Rejected Google token with unexpected issuer: %s", info.get("iss"))
        return None

    return info


def build_google_auth_url(state: str = "") -> str:
    """Build the Google OAuth authorize URL for the server redirect flow."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "access_type": "online",
    }
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_google_code(code: str) -> Optional[Dict[str, object]]:
    """
    Exchange an authorization code for Google tokens and return the verified
    ID-token claims. Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and
    GOOGLE_REDIRECT_URI to be configured.
    """
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET and settings.GOOGLE_REDIRECT_URI):
        logger.error("Google redirect flow is not fully configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            tokens = resp.json()
    except Exception as exc:
        logger.error("Google authorization-code exchange failed: %s", exc)
        return None

    google_id_token = tokens.get("id_token")
    if not google_id_token:
        logger.error("Google token exchange did not return an id_token")
        return None

    return verify_google_id_token(google_id_token)
