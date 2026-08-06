"""
Database Configuration
Async SQLAlchemy 2.0 setup with connection pooling and session management.
"""

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Create async engine
#
# Memory optimization: each pooled asyncpg connection holds its own buffers,
# greenlet state and protocol objects. The previous pool (20 + 30 overflow = up
# to 50 connections) could consume ~100+ MB on Render's 512 MB free tier. A
# smaller pool (5 + 5 overflow) is ample for this workload — FastAPI requests
# use one short-lived session each and the two background schedulers use one
# session at a time — while keeping memory in check.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQLALCHEMY_ECHO,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=5,
    max_overflow=5,
    connect_args={"server_settings": {"jit": "off"}},
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Base class for models
class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_session() -> AsyncSession:
    """
    Dependency to get async database session.
    Yields a new session for each request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()