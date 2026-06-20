from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(100),
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