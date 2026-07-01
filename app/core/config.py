"""
Core Configuration
Environment variables and settings management using Pydantic.
"""

from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Application
    APP_NAME: str = "InvestorDocs AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:Welcome123!@localhost:5432/InvestorDocs"
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

    # Security
    PASSWORD_MIN_LENGTH: int = 8
    BCRYPT_ROUNDS: int = 12

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # AI/RAG (Future)
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    QDRANT_URL: str = "http://localhost:6333"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_PASSWORD: str = ""
    SMTP_EMAIL: str = ""
    FRONTEND_URL:str

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()