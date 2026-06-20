from uuid import uuid4
from typing import Optional

from sqlalchemy import (
    JSON,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Embedding(Base):
    """Vector embedding for RAG chunks."""

    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    chunk_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=False),
        ForeignKey("rag_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    embedding: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    # Relationships
    chunk: Mapped[Optional["RAGChunk"]] = relationship(
        back_populates="embedding",
    )

    def __repr__(self) -> str:
        return f"<Embedding(chunk_id={self.chunk_id})>"
