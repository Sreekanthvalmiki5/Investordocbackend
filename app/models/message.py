from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Message(Base):
    """Message model."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    conversation_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    model: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    liked: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Relationships
    conversation: Mapped[Optional["Conversation"]] = relationship(
        back_populates="messages",
    )

    sources: Mapped[List["MessageSource"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"


class MessageSource(Base):
    """Message source/citation model."""

    __tablename__ = "message_sources"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    message_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    page: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Relationships
    message: Mapped[Optional["Message"]] = relationship(
        back_populates="sources",
    )

    document: Mapped[Optional["Document"]] = relationship(
        back_populates="message_sources",
    )

    def __repr__(self) -> str:
        return f"<MessageSource(id={self.id}, title={self.title})>"




