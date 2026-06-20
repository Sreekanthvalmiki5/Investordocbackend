from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Document(Base):
    """Document model."""

    __tablename__ = "documents"

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

    name: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    quarter: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    year: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    size_mb: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    uploaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    file_url: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    source_url: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    starred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    # Relationships
    company: Mapped[Optional["Company"]] = relationship(
        back_populates="documents",
    )

    message_sources: Mapped[List["MessageSource"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    rag_chunks: Mapped[List["RAGChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, name={self.name})>"