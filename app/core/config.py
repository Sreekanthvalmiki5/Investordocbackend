"""
Core Configuration
Environment variables and settings management using Pydantic.
"""

from typing import List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import os

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Application
    APP_NAME: str = "InvestorDocs AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/investordocs"
    SQLALCHEMY_ECHO: bool = False

    # JWT
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # ------------------------------------------------------------------
    # CORS: auto-allow the frontend origin
    # ------------------------------------------------------------------
    # The browser blocks cross-origin API calls unless the frontend origin is
    # listed in allow_origins. Rather than hardcoding the production domain in
    # the CORS_ORIGINS list above, FRONTEND_URL (set in the environment / .env)
    # is merged in automatically. No trailing slash, no duplicates.
    @model_validator(mode="after")
    def _merge_frontend_origin(self) -> "Settings":
        if self.FRONTEND_URL:
            origin = self.FRONTEND_URL.strip().rstrip("/")
            if origin and origin not in self.CORS_ORIGINS:
                self.CORS_ORIGINS = [*self.CORS_ORIGINS, origin]
        return self

    # Security
    PASSWORD_MIN_LENGTH: int = 8
    BCRYPT_ROUNDS: int = 12

    # Google OAuth (ID-token + server-side redirect flows)
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "")

    # Email verification
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24

    # Email retry scheduler (failed emails are persisted to the outbox table
    # and re-sent in the background every EMAIL_RETRY_INTERVAL_MINUTES).
    EMAIL_RETRY_INTERVAL_MINUTES: int = 10
    EMAIL_MAX_RETRIES: int = 5
    EMAIL_RETRY_BATCH_SIZE: int = 100
    # Delivered/given-up outbox rows older than this are purged by the
    # scheduler so the table cannot grow unboundedly.
    EMAIL_OUTBOX_RETENTION_DAYS: int = 7

    # Login notification emails
    LOGIN_NOTIFICATION_ENABLED: bool = True
    IP_GEOLOCATION_ENABLED: bool = True

    # Media uploads (voice queries / image analysis)
    MAX_AUDIO_UPLOAD_MB: int = 25
    MAX_IMAGE_UPLOAD_MB: int = 10

    # Speech-to-text (Faster-Whisper, fully local — no OpenAI key required)
    # Model sizes: tiny | base | small | medium | large-v3
    WHISPER_MODEL: str = "small"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # Vision model
    VISION_MODEL: str = "openai/gpt-4o-mini"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # AI/RAG (Future)
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_API_BASE: str = "https://api.openrouter.ai/v1"
    QDRANT_URL: str = "http://localhost:6333"

    # Vector store (PGVector)
    VECTOR_DB_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/investordocs"
    VECTOR_COLLECTION_NAME: str = "investordocs"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # AWS / S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_ACCESS_KEY: str = ""
    AWS_SECRET_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_BUCKET_NAME: str = ""
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_PASSWORD: str = ""
    SMTP_EMAIL: str = ""
    FRONTEND_URL:str

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    # ------------------------------------------------------------------
    # URL normalization
    # ------------------------------------------------------------------
    # Render/Heroku/Neon expose DATABASE_URL as a bare `postgres://...` URL
    # with no driver. SQLAlchemy then defaults to the SYNC psycopg2 dialect,
    # which is not installed (and can never be used with create_async_engine).
    # Force the asyncpg driver here so the async engine works out of the box.
    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        v = _force_driver(v, "asyncpg")
        # The SQLAlchemy asyncpg dialect does NOT understand sslmode=... (it
        # forwards unknown query params straight to asyncpg.connect and crashes
        # with "TypeError: connect() got an unexpected keyword argument
        # 'sslmode'"). It expects ssl=... instead. Neon/Render URLs commonly
        # carry ?sslmode=require, so translate it here.
        return _rename_query_param(v, "sslmode", "ssl")

    # Same idea for the vector-store connection: force the psycopg v3 driver
    # (used by langchain_postgres.PGVector).
    @field_validator("VECTOR_DB_URL")
    @classmethod
    def _normalize_vector_db_url(cls, v: str) -> str:
        return _force_driver(v, "psycopg")


def _force_driver(url: str, driver: str) -> str:
    """Prefix a postgres URL with the given SQLAlchemy driver if missing."""
    if url.startswith("postgresql://"):
        return f"postgresql+{driver}://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return f"postgresql+{driver}://" + url[len("postgres://"):]
    return url


def _rename_query_param(url: str, old_key: str, new_key: str) -> str:
    """Rename one query-string parameter (e.g. sslmode -> ssl).

    If the new key is already present, the old key is dropped instead so a
    leftover sslmode can never be forwarded to the asyncpg driver.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = parse_qsl(parts.query, keep_blank_values=True)
    new_key_present = any(key == new_key for key, _ in query)
    renamed = []
    for key, value in query:
        if key == old_key and not new_key_present:
            renamed.append((new_key, value))
        elif key != old_key:
            renamed.append((key, value))
    if renamed == query:
        return url
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(renamed), parts.fragment)
    )


settings = Settings()


def is_openrouter_key(key: str) -> bool:
    """Return True if the API key looks like an OpenRouter key (sk-or-...)."""
    return key.strip().startswith("sk-or-")