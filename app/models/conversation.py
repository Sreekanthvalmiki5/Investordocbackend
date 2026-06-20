from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Conversation(Base):
    """Conversation model."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    company_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("companies.id"),
        nullable=True,
        index=True,
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    pinned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        back_populates="conversations",
    )

    company: Mapped[Optional["Company"]] = relationship(
        back_populates="conversations",
    )

    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"