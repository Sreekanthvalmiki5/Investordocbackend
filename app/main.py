"""
InvestorDocs AI Backend - Main Application
Production-ready FastAPI application with comprehensive middleware and error handling.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, bookmarks, chat, companies, conversations, documents, insights, messages, users
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.logging import setup_logging
from app.core.migrations import run_startup_migrations
from app.services.services import DocumentService
from app.services.transcription_service import TranscriptionService

# Setup structured logging
setup_logging()
logger = logging.getLogger(__name__)


async def _embedding_scheduler_loop(app: FastAPI):
    interval = 1800  # 30 minutes
    logger.info(f"Embedding scheduler started, running every {interval} seconds")
    while True:
        try:
            async with AsyncSessionLocal() as session:
                service = DocumentService(session)
                processed = await service.process_pending_documents(limit=200)
                if processed:
                    logger.info(f"Embedding scheduler processed {processed} pending documents")
                else:
                    logger.info("Embedding scheduler found no pending documents")
        except Exception as exc:
            logger.error(f"Embedding scheduler error: {exc}", exc_info=exc)
        await asyncio.sleep(interval)


async def _transcription_warmup(app: FastAPI):
    """
    Pre-load the Faster-Whisper model in the background at startup.

    Runs off the event loop so startup is not blocked, and the model is ready
    by the time the first voice request arrives (avoiding the download/load
    cost — and the risk of hitting the frontend's upload timeout — on first
    use). The singleton guarantees it is loaded exactly once.
    """
    try:
        await asyncio.to_thread(TranscriptionService.get_instance()._load_model)
        logger.info("Transcription model warm-up complete")
    except Exception as exc:
        logger.warning(
            "Transcription model warm-up failed; it will load on first request: %s",
            exc,
        )


async def _email_retry_loop(app: FastAPI):
    """
    Retry emails that failed to send (persisted in the email_outbox table).

    Runs every EMAIL_RETRY_INTERVAL_MINUTES (default 10) and re-sends every
    pending outbox row whose next_attempt_at has passed. Uses SELECT ... FOR
    UPDATE SKIP LOCKED so multiple app workers never send the same email twice.

    Delivery is at-least-once: if the process crashes after SMTP accepts the
    email but before the row is marked sent, the email is sent again on a later
    retry. For transactional emails (single-use verification/reset links) a rare
    duplicate is preferable to a lost email.
    """
    from app.models.email_outbox import EmailOutbox
    from app.services.email_service import EmailService

    interval = settings.EMAIL_RETRY_INTERVAL_MINUTES * 60
    logger.info(
        "Email retry scheduler started, running every %s seconds", interval
    )
    email_service = EmailService()

    while True:
        try:
            now = datetime.utcnow()
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(EmailOutbox)
                    .where(
                        EmailOutbox.status == "pending",
                        EmailOutbox.next_attempt_at <= now,
                    )
                    .order_by(EmailOutbox.created_at.asc())
                    .limit(settings.EMAIL_RETRY_BATCH_SIZE)
                    .with_for_update(skip_locked=True)
                )
                rows = (await session.execute(stmt)).scalars().all()

                sent = 0
                for row in rows:
                    try:
                        await email_service.send_outbox_message(
                            row.recipient,
                            row.subject,
                            row.plain_text,
                            row.html,
                        )
                        row.status = "sent"
                        row.last_error = None
                        sent += 1
                    except Exception as exc:
                        row.attempts += 1
                        row.last_error = str(exc)[:1000]
                        # Password-reset links expire after 30 minutes, so cap
                        # their retries (max ~20 min of delay) to avoid
                        # delivering an already-expired link.
                        max_attempts = (
                            2
                            if row.email_type == "password_reset"
                            else settings.EMAIL_MAX_RETRIES
                        )
                        if row.attempts >= max_attempts:
                            row.status = "failed"
                            logger.error(
                                "Email permanently failed after %s attempts "
                                "(%s -> %s): %s",
                                row.attempts,
                                row.email_type,
                                row.recipient,
                                exc,
                            )
                        else:
                            row.next_attempt_at = datetime.utcnow() + timedelta(
                                minutes=settings.EMAIL_RETRY_INTERVAL_MINUTES
                            )

                # Housekeeping: purge old sent/failed rows so the outbox table
                # cannot grow unboundedly over months of logins.
                await session.execute(
                    delete(EmailOutbox).where(
                        EmailOutbox.status.in_(["sent", "failed"]),
                        EmailOutbox.updated_at
                        < datetime.utcnow()
                        - timedelta(days=settings.EMAIL_OUTBOX_RETENTION_DAYS),
                    )
                )

                await session.commit()
                if rows:
                    logger.info(
                        "Email retry scheduler: delivered %s/%s queued emails "
                        "(%s still pending/failed)",
                        sent,
                        len(rows),
                        len(rows) - sent,
                    )
        except Exception as exc:
            logger.error(f"Email retry scheduler error: {exc}", exc_info=exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info(f"Starting InvestorDocs AI Backend - Environment: {settings.ENVIRONMENT}")
    
    # Startup: apply idempotent column migrations before create_all so existing
    # deployments receive the new User columns (Google OAuth, email verification,
    # last-login tracking).
    await run_startup_migrations(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.embedding_scheduler_task = asyncio.create_task(_embedding_scheduler_loop(app))
    app.state.email_retry_task = asyncio.create_task(_email_retry_loop(app))
    app.state.transcription_warmup = asyncio.create_task(_transcription_warmup(app))
    
    yield
    
    # Shutdown
    logger.info("Shutting down InvestorDocs AI Backend")
    for task_name in ("embedding_scheduler_task", "email_retry_task", "transcription_warmup"):
        if hasattr(app.state, task_name):
            task = getattr(app.state, task_name)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    await engine.dispose()


# Initialize FastAPI app
app = FastAPI(
    title="InvestorDocs AI Backend",
    description="Enterprise-grade financial research platform API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An internal server error occurred. Please try again later.",
        },
    )


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "InvestorDocs AI Backend"}


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(companies.router, prefix="/api/companies", tags=["Companies"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["Conversations"])
app.include_router(messages.router, prefix="/api/conversations", tags=["Messages"])
app.include_router(messages.messages_router, prefix="/api/messages", tags=["Messages"])
app.include_router(bookmarks.router, prefix="/api/bookmarks", tags=["Bookmarks"])
app.include_router(insights.router, prefix="/api/insights", tags=["AI Insights"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )