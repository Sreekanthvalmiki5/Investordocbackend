from datetime import datetime
from uuid import uuid4
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RAGChunk(Base):
    """RAG chunk for vector embeddings."""

    __tablename__ = "rag_chunks"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    document_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    company_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )

    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    chunk_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Relationships
    document: Mapped[Optional["Document"]] = relationship(
        back_populates="rag_chunks",
    )

    company: Mapped[Optional["Company"]] = relationship(
        back_populates="rag_chunks",
    )

    embedding: Mapped[Optional["Embedding"]] = relationship(
        back_populates="chunk",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<RAGChunk(id={self.id}, page={self.page_number})>"