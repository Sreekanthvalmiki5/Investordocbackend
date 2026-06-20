from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Company(Base):
    """Company model."""

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    ticker: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    sector: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    industry: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    market_cap_cr: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    latest_filing_date: Mapped[Optional[datetime]] = mapped_column(
        Date,
        nullable=True,
    )

    total_reports: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    color: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Relationships
    documents: Mapped[List["Document"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    insights: Mapped[List["AIInsight"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    rag_chunks: Mapped[List["RAGChunk"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name={self.name})>"
