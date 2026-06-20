"""
Pydantic v2 Schemas
Request and response models with validation.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field, validator


# ============================================================================
# Auth Schemas
# ============================================================================

class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    """Login request model."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class RegisterRequest(BaseModel):
    """Register request model."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class AuthResponse(BaseModel):
    """Auth response wrapper."""

    success: bool
    message: str
    data: Optional[TokenResponse] = None


# ============================================================================
# User Schemas
# ============================================================================

class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema."""

    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """User update schema."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None


class UserResponse(UserBase):
    """User response schema."""

    id: str
    auth_provider: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


# ============================================================================
# Company Schemas
# ============================================================================

class CompanyBase(BaseModel):
    """Base company schema."""

    id: str
    name: str
    ticker: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_cr: Optional[int] = None
    description: Optional[str] = None
    color: Optional[str] = None


class CompanyResponse(CompanyBase):
    """Company response schema."""

    latest_filing_date: Optional[datetime]
    total_reports: int
    created_at: datetime

    class Config:
        from_attributes = True


class CompanyListResponse(BaseModel):
    """Paginated company list response."""

    success: bool
    page: int
    limit: int
    total: int
    items: List[CompanyResponse]


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentBase(BaseModel):
    """Base document schema."""

    company_id: str
    name: Optional[str] = None
    type: Optional[str] = None
    quarter: Optional[str] = None
    year: Optional[int] = None
    page_count: Optional[int] = None
    size_mb: Optional[float] = None


class DocumentCreate(DocumentBase):
    """Document creation schema."""

    file_url: str
    source_url: Optional[str] = None


class DocumentUpdate(BaseModel):
    """Document update schema."""

    name: Optional[str] = None
    starred: Optional[bool] = None


class DocumentResponse(DocumentBase):
    """Document response schema."""

    id: str
    uploaded_at: Optional[datetime]
    file_url: str
    source_url: Optional[str]
    starred: bool

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    success: bool
    page: int
    limit: int
    total: int
    items: List[DocumentResponse]


# ============================================================================
# Conversation Schemas
# ============================================================================

class ConversationBase(BaseModel):
    """Base conversation schema."""

    title: Optional[str] = None
    company_id: Optional[str] = None


class ConversationCreate(ConversationBase):
    """Conversation creation schema."""

    pass


class ConversationUpdate(BaseModel):
    """Conversation update schema."""

    title: Optional[str] = None
    pinned: Optional[bool] = None
    archived: Optional[bool] = None


class ConversationResponse(ConversationBase):
    """Conversation response schema."""

    id: str
    pinned: bool
    archived: bool
    message_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """Paginated conversation list response."""

    success: bool
    page: int
    limit: int
    total: int
    items: List[ConversationResponse]


# ============================================================================
# Message Schemas
# ============================================================================

class MessageSourceResponse(BaseModel):
    """Message source response schema."""

    id: str
    document_id: Optional[str]
    title: Optional[str]
    page: Optional[int]

    class Config:
        from_attributes = True


class MessageBase(BaseModel):
    """Base message schema."""

    content: str = Field(..., min_length=1)


class MessageCreate(MessageBase):
    """Message creation schema."""

    role: str = Field(..., pattern="^(user|assistant)$")
    model: Optional[str] = None


class MessageUpdate(BaseModel):
    """Message update schema."""

    liked: Optional[bool] = None


class MessageResponse(BaseModel):
    """Message response schema."""

    id: str
    conversation_id: str
    role: str
    content: str
    model: Optional[str]
    liked: Optional[bool]
    sources: List[MessageSourceResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Paginated message list response."""

    success: bool
    items: List[MessageResponse]


# ============================================================================
# Bookmark Schemas
# ============================================================================

class BookmarkBase(BaseModel):
    """Base bookmark schema."""

    kind: str = Field(..., pattern="^(document|message|company)$")
    ref_id: str
    title: Optional[str] = None
    subtitle: Optional[str] = None


class BookmarkCreate(BookmarkBase):
    """Bookmark creation schema."""

    pass


class BookmarkResponse(BookmarkBase):
    """Bookmark response schema."""

    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class BookmarkListResponse(BaseModel):
    """Paginated bookmark list response."""

    success: bool
    page: int
    limit: int
    total: int
    items: List[BookmarkResponse]


# ============================================================================
# AI Insight Schemas
# ============================================================================

class AIInsightBase(BaseModel):
    """Base insight schema."""

    kind: str
    title: str
    summary: Optional[str] = None
    details: Optional[dict] = None
    sentiment: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class AIInsightResponse(AIInsightBase):
    """Insight response schema."""

    id: str
    company_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class AIInsightListResponse(BaseModel):
    """Paginated insight list response."""

    success: bool
    page: int
    limit: int
    total: int
    items: List[AIInsightResponse]


# ============================================================================
# Chat Schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Chat request schema."""

    message: str = Field(..., min_length=1, max_length=5000)
    company_id: Optional[str] = None
    model: Optional[str] = "gpt-4"
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response schema."""

    success: bool
    message: str
    data: Optional[MessageResponse] = None


# ============================================================================
# Generic Response Wrappers
# ============================================================================

class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    """Generic error response."""

    success: bool = False
    message: str