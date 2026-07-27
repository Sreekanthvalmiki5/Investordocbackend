from uuid import uuid4
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.database import Base


class Embedding(Base):
    """
    Vector embedding for RAG chunks.

    Uses pgvector's native Vector type for efficient similarity search
    via the <=> (cosine distance) operator directly in PostgreSQL.
    """

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

    # Native pgvector column for similarity search
    embedding_vector: Mapped[list] = mapped_column(
        Vector(settings.EMBEDDING_DIMENSION or 1536),
        nullable=False,
    )

    # Relationships
    chunk: Mapped[Optional["RAGChunk"]] = relationship(
        back_populates="embedding",
    )

    def __repr__(self) -> str:
        return f"<Embedding(chunk_id={self.chunk_id})>"
