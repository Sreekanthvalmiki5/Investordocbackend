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
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQLALCHEMY_ECHO,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
    poolclass=pool.AsyncAdaptedQueuePool,
    pool_size=20,
    max_overflow=30,
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