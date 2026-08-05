"""
Email Outbox Model

Persists emails that failed to send (SMTP errors, outages, bad credentials) so a
background scheduler can retry them later instead of silently losing them.

Lifecycle:
  - status "pending" : created on delivery failure, eligible for retry
  - status "sent"    : delivered successfully by the retry scheduler
  - status "failed"  : exhausted retries, gave up permanently
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        # Composite index matching the retry scheduler's query:
        #   WHERE status = 'pending' AND next_attempt_at <= now
        Index("ix_email_outbox_status_next_attempt", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    recipient: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    plain_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    email_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="generic",
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        index=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
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
