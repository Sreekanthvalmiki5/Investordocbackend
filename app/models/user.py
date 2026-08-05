from datetime import datetime
from uuid import uuid4
from typing import Optional, List

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

from uuid import UUID, uuid4
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
class User(Base):
    __tablename__ = "users"



    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    first_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    last_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    image_url: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    auth_provider: Mapped[str] = mapped_column(
        String(50),
        default="email",
    )

    # Google OAuth
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )

    avatar_url: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )

    verification_token: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    verification_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Last login tracking (used for login notification emails)
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    last_login_device: Mapped[Optional[str]] = mapped_column(
        String(255),
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
    role: Mapped[str] = mapped_column(
        String(20),
        default="user",
        nullable=False,
    )

    plan: Mapped[str] = mapped_column(
        String(20),
        default="free",
        nullable=False,
    )

    # Relationships
    conversations: Mapped[List["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    bookmarks: Mapped[List["Bookmark"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
