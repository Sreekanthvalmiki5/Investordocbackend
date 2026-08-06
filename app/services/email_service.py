"""
Email Service

Sends transactional emails via SMTP (aiosmtplib):
  - Password reset
  - Email verification (24h expiry)
  - Login notifications (time, browser, device, IP, city/country, suspicious flag)

Also provides a fire-and-forget helper so emails never block the request that
triggered them (registration, login, etc.).
"""

import asyncio
import logging
import re
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import aiosmtplib
import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.request_utils import is_public_ip
from app.models.email_outbox import EmailOutbox

logger = logging.getLogger(__name__)

# Strong references to in-flight background tasks so they are not garbage
# collected mid-send.
_background_tasks: "set[asyncio.Task]" = set()

# Shared HTTP client for IP geolocation (memory optimization). Building a fresh
# AsyncClient (connection pool) for every login-notification lookup would waste
# memory; one process-wide client is reused instead.
_http_client: "Optional[httpx.AsyncClient]" = None
_http_client_lock = asyncio.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    """Return the process-wide shared AsyncClient (created once, never closed)."""
    global _http_client
    if _http_client is None:
        async with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.AsyncClient(timeout=3.0)
    return _http_client

# ---------------------------------------------------------------------------
# Background email helper
# ---------------------------------------------------------------------------


def _log_task_error(task: "asyncio.Task") -> None:
    """Log exceptions raised by background email tasks (and drop the reference)."""
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background email task failed: %s", exc, exc_info=exc)


def send_email_background(coro: Any) -> None:
    """Schedule an async email send without awaiting it (fire-and-forget)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_log_task_error)


# ---------------------------------------------------------------------------
# User-Agent parsing (lightweight, no external dependency)
# ---------------------------------------------------------------------------


def parse_user_agent(user_agent: str) -> Dict[str, str]:
    """
    Extract a best-effort browser / OS / device description from a User-Agent
    header. Never raises; returns sensible defaults for unknown agents.
    """
    ua = user_agent or ""

    # Browser
    browser = "Unknown browser"
    if "Edg/" in ua:
        browser = "Microsoft Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Chrome/" in ua and "Chromium" not in ua:
        browser = "Google Chrome"
    elif "Firefox/" in ua:
        browser = "Mozilla Firefox"
    elif "Safari/" in ua and "Chrome/" not in ua:
        browser = "Safari"
    elif "MSIE" in ua or "Trident/" in ua:
        browser = "Internet Explorer"

    # OS
    os_name = "Unknown OS"
    if "Windows NT 10" in ua:
        os_name = "Windows 10/11"
    elif "Windows NT 6.3" in ua:
        os_name = "Windows 8.1"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"

    # Device
    if re.search(r"iPhone|iPad|iPod|Android.*Mobile|Mobile", ua):
        device = "Mobile"
    elif re.search(r"iPad|Tablet", ua):
        device = "Tablet"
    elif "Mobi" in ua:
        device = "Mobile"
    else:
        device = "Desktop"

    return {"browser": browser, "os": os_name, "device": device}


# ---------------------------------------------------------------------------
# IP geolocation (optional, free tier)
# ---------------------------------------------------------------------------


async def geolocate_ip(ip: str) -> Optional[Dict[str, str]]:
    """
    Resolve a public IP to a city/country using the free ip-api.com endpoint.

    Returns None when geolocation is disabled, the IP is private/local, or the
    lookup fails -- the caller should treat that as "location unknown".
    """
    if not settings.IP_GEOLOCATION_ENABLED:
        return None
    if not is_public_ip(ip):
        return None

    try:
        # Reuse the process-wide client instead of creating a new one per call.
        resp = await (await _get_http_client()).get(f"http://ip-api.com/json/{ip}")
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            return None
        return {
            "city": str(data.get("city") or ""),
            "country": str(data.get("country") or ""),
        }
    except Exception:
        return None


class EmailService:

    async def _send(self, message: EmailMessage) -> None:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            start_tls=True,
            username=settings.SMTP_EMAIL,
            password=settings.SMTP_PASSWORD,
            # Bound the connect/command timeouts so a hung SMTP server cannot
            # stall a request handler or the retry scheduler indefinitely.
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Delivery with retry-outbox fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _build_message(
        recipient: str,
        subject: str,
        plain_text: str,
        html: Optional[str],
    ) -> EmailMessage:
        """Build a multipart EmailMessage from stored parts."""
        message = EmailMessage()
        message["From"] = settings.SMTP_EMAIL
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(plain_text)
        if html:
            message.add_alternative(html, subtype="html")
        return message

    async def send_outbox_message(
        self,
        recipient: str,
        subject: str,
        plain_text: str,
        html: Optional[str],
    ) -> None:
        """
        Send an email straight from outbox parts (used by the retry scheduler).

        Raises on SMTP failure so the caller can update the outbox row.
        """
        await self._send(self._build_message(recipient, subject, plain_text, html))

    async def _deliver(
        self,
        recipient: str,
        subject: str,
        plain_text: str,
        html: Optional[str],
        email_type: str,
    ) -> bool:
        """
        Send an email; if SMTP fails, persist it to the outbox for the retry
        scheduler instead of losing it (and instead of failing the request).

        Returns True when delivered immediately, False when queued for retry.
        """
        try:
            await self.send_outbox_message(recipient, subject, plain_text, html)
            return True
        except Exception as exc:
            logger.warning(
                "Email delivery failed (%s -> %s), queued for retry: %s",
                email_type,
                recipient,
                exc,
            )
            await self._enqueue_outbox(
                recipient=recipient,
                subject=subject,
                plain_text=plain_text,
                html=html,
                email_type=email_type,
                error=str(exc),
            )
            return False

    async def _enqueue_outbox(
        self,
        recipient: str,
        subject: str,
        plain_text: str,
        html: Optional[str],
        email_type: str,
        error: str,
    ) -> None:
        """Persist a failed email so the background scheduler can retry it."""
        try:
            async with AsyncSessionLocal() as session:
                session.add(
                    EmailOutbox(
                        recipient=recipient,
                        subject=subject,
                        plain_text=plain_text,
                        html=html,
                        email_type=email_type,
                        last_error=error[:1000],
                    )
                )
                await session.commit()
        except Exception as exc:
            # Last-resort guard: if the outbox write fails (e.g. DB down) we
            # cannot do anything more than log.
            logger.error(
                "Failed to persist email to outbox (%s -> %s): %s",
                email_type,
                recipient,
                exc,
                exc_info=exc,
            )

    # ------------------------------------------------------------------
    # Password reset (existing)
    # ------------------------------------------------------------------

    async def send_password_reset(
        self,
        email: str,
        first_name: str,
        reset_link: str,
    ):

        html = f"""
        <html>

        <body
        style="
        font-family:Arial;
        max-width:650px;
        margin:auto;
        padding:30px;
        ">

            <h2>Hello {first_name},</h2>

            <p>
            We received a request to reset your password.
            </p>

            <p>
            Click the button below to reset it.
            </p>

            <p>

            <a
                href="{reset_link}"
                style="
                    background:#2563eb;
                    color:white;
                    padding:14px 24px;
                    text-decoration:none;
                    border-radius:8px;
                    display:inline-block;
                "
            >
                Reset Password
            </a>

            </p>

            <p>
            This link expires in 30 minutes.
            </p>

            <hr>

            <p style="font-size:13px;color:gray">
            If you didn't request this password reset,
            you can safely ignore this email.
            </p>

            <br>

            <strong>InvestorDocs AI</strong>

        </body>

        </html>
        """

        return await self._deliver(
            recipient=email,
            subject="Reset your InvestorDocs password",
            plain_text=f"Reset your password here:\n\n{reset_link}",
            html=html,
            email_type="password_reset",
        )

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------

    async def send_verification_email(
        self,
        email: str,
        first_name: str,
        verify_link: str,
    ):
        """Send an email-verification link (expires after 24 hours)."""
        html = f"""
        <html>
        <body style="font-family:Arial;max-width:650px;margin:auto;padding:30px;">
            <h2>Welcome to InvestorDocs AI, {first_name}!</h2>
            <p>Please confirm your email address to activate your account and start
            analyzing financial documents.</p>
            <p>
            <a href="{verify_link}" style="background:#2563eb;color:white;padding:14px 24px;
                text-decoration:none;border-radius:8px;display:inline-block;">
                Verify Email
            </a>
            </p>
            <p>This link expires in 24 hours. If it expires,
            <a href="{settings.FRONTEND_URL}/#/login">log in</a> and use the
            "Resend verification email" option.</p>
            <hr>
            <p style="font-size:13px;color:gray">
            If you didn't create this account, you can safely ignore this email.
            </p>
            <br>
            <strong>InvestorDocs AI</strong>
        </body>
        </html>
        """

        return await self._deliver(
            recipient=email,
            subject="Verify your InvestorDocs email address",
            plain_text=(
                f"Verify your email address here:\n\n{verify_link}\n\n"
                "This link expires in 24 hours."
            ),
            html=html,
            email_type="verification",
        )

    # ------------------------------------------------------------------
    # Login notification
    # ------------------------------------------------------------------

    async def send_login_notification(
        self,
        email: str,
        first_name: str,
        login_time: datetime,
        ip: Optional[str],
        user_agent: str,
        previous_device: Optional[str] = None,
        previous_ip: Optional[str] = None,
        previous_login_at: Optional[datetime] = None,
    ):
        """
        Send a "new sign-in" email with time, browser, OS, device, IP, and
        city/country (when resolvable). Highlights the login when it looks
        suspicious (new device and/or new country).
        """
        ua_info = parse_user_agent(user_agent)
        browser = ua_info["browser"]
        os_name = ua_info["os"]
        device = ua_info["device"]

        # Resolve locations for the current and previous IPs (best effort).
        location: Optional[Dict[str, str]] = await geolocate_ip(ip or "")
        previous_location: Optional[Dict[str, str]] = None
        if previous_ip and previous_ip != ip:
            previous_location = await geolocate_ip(previous_ip)

        location_str = self._format_location(location)

        # Suspicious heuristics.
        reasons: List[str] = []
        if previous_device and previous_device != device:
            reasons.append(f"a new device ({device}) was used")
        if (
            previous_location
            and location
            and previous_location.get("country")
            and previous_location.get("country") != location.get("country")
        ):
            reasons.append(
                "the login country changed ("
                f"{previous_location.get('country')} -> {location.get('country')})"
            )

        suspicious = len(reasons) > 0
        summary = "; ".join(reasons) if reasons else "This login looks normal."

        login_time_str = login_time.strftime("%B %d, %Y at %I:%M %p UTC")
        previous_str = (
            previous_login_at.strftime("%B %d, %Y at %I:%M %p UTC")
            if previous_login_at
            else "First login"
        )

        banner = ""
        if suspicious:
            banner = (
                '<div style="background:#fef2f2;border:1px solid #fecaca;color:#b91c1c;'
                'padding:12px 16px;border-radius:8px;margin:16px 0;">'
                "<strong>!! Suspicious login detected.</strong> "
                "If this wasn't you, reset your password immediately."
                "</div>"
            )

        subject = "!! New sign-in to InvestorDocs" if suspicious else "New sign-in to InvestorDocs"

        html = f"""
        <html>
        <body style="font-family:Arial;max-width:650px;margin:auto;padding:30px;">
            <h2>Hi {first_name},</h2>
            <p>We noticed a new sign-in to your InvestorDocs AI account.</p>
            {banner}
            <table style="border-collapse:collapse;width:100%;max-width:480px;">
                <tr><td style="padding:8px 0;color:#6b7280;">Sign-in time</td>
                    <td style="padding:8px 0;font-weight:600;">{login_time_str}</td></tr>
                <tr><td style="padding:8px 0;color:#6b7280;">Browser</td>
                    <td style="padding:8px 0;font-weight:600;">{browser}</td></tr>
                <tr><td style="padding:8px 0;color:#6b7280;">Operating system</td>
                    <td style="padding:8px 0;font-weight:600;">{os_name}</td></tr>
                <tr><td style="padding:8px 0;color:#6b7280;">Device</td>
                    <td style="padding:8px 0;font-weight:600;">{device}</td></tr>
                <tr><td style="padding:8px 0;color:#6b7280;">IP address</td>
                    <td style="padding:8px 0;font-weight:600;">{ip or "Unknown"}</td></tr>
                <tr><td style="padding:8px 0;color:#6b7280;">Location</td>
                    <td style="padding:8px 0;font-weight:600;">{location_str}</td></tr>
                <tr><td style="padding:8px 0;color:#6b7280;">Previous sign-in</td>
                    <td style="padding:8px 0;font-weight:600;">{previous_str}</td></tr>
            </table>
            <p style="font-size:13px;color:#374151;">{summary}</p>
            <hr>
            <p style="font-size:13px;color:gray">
            Not you? <a href="{settings.FRONTEND_URL}/#/forgot-password">Reset your password</a>
            and contact support immediately.
            </p>
            <br>
            <strong>InvestorDocs AI</strong>
        </body>
        </html>
        """

        return await self._deliver(
            recipient=email,
            subject=subject,
            plain_text=(
                f"New sign-in to your InvestorDocs account.\n\n"
                f"Time: {login_time_str}\nBrowser: {browser}\nOS: {os_name}\n"
                f"Device: {device}\nIP: {ip or 'Unknown'}\nLocation: {location_str}\n\n"
                f"{summary}"
            ),
            html=html,
            email_type="login_notification",
        )

    @staticmethod
    def _format_location(location: Optional[Dict[str, str]]) -> str:
        if not location:
            return "Unknown"
        parts = [p for p in (location.get("city"), location.get("country")) if p]
        return ", ".join(parts) if parts else "Unknown"
