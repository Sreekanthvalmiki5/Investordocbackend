from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    JSON,
    Numeric,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AIInsight(Base):
    __tablename__ = "ai_insights"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    company_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    details: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )

    sentiment: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 2),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Relationships
    company: Mapped[Optional["Company"]] = relationship(
        back_populates="insights",
    )

    def __repr__(self) -> str:
        return f"<AIInsight(id={self.id}, kind={self.kind})>"