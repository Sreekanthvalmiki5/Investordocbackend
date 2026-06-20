from datetime import datetime
from uuid import uuid4
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QueryCache(Base):
    """Cache for frequently asked questions."""

    __tablename__ = "query_cache"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    company_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("companies.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<QueryCache(company_id={self.company_id})>"