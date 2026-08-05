from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    # users.id is a PostgreSQL UUID, and the bookmarks.user_id column in
    # existing databases is `uuid`. Mapping it as String(100) caused
    # "operator does not exist: uuid = character varying" on every query.
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    ref_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    subtitle: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        back_populates="bookmarks",
    )

    def __repr__(self) -> str:
        return f"<Bookmark(id={self.id}, kind={self.kind})>"