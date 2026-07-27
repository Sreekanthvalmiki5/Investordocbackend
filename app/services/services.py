"""
Service Layer
Business logic layer with repository injection.
"""

import asyncio
import httpx
import secrets
import uuid
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse

from openai import OpenAI
from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.password_reset import PasswordResetToken
from app.services.s3_service import S3Service

from app.models.insight import AIInsight
from app.models.bookmark import  Bookmark
from app.models.company import Company
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.embedding import Embedding
from app.models.message import Message
from app.models.message import MessageSource
from app.models.rag_chunk import RAGChunk
from app.models.user import  User
from app.services.email_service import EmailService
from app.core.config import settings

from app.repositories.repositories import (
    AIInsightRepository,
    BookmarkRepository,
    CompanyRepository,
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
    MessageSourceRepository,
    UserRepository,
    PasswordResetRepository
)
from app.schemas.schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationUpdate,
    DocumentCreate,
    DocumentUpdate,
    LoginRequest,
    MessageCreate,
    RegisterRequest,
    UserUpdate,
    ResetPasswordRequest
)
from app.core.security import create_access_token, hash_password, verify_password


class AuthService:
    """Authentication service."""

    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)
        self.session = session
        self.reset_repo = PasswordResetRepository(session)
        self.email_service = EmailService()

    async def register(self, request: RegisterRequest) -> User:
        """Register a new user."""
        # Check if user exists
        existing = await self.user_repo.get_by_email(request.email)
        print("Existing user:", existing) 
        if existing:
            raise ValueError(
        "An account with this email already exists. Please sign in or reset your password."
    )

        # Create user
        user = User(
          
            email=request.email,
            password_hash=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            auth_provider="email",
        )

        return await self.user_repo.create(user)

    async def login(self, request: LoginRequest) -> Tuple[User, str]:
        """Login user and return user + access token."""
        user = await self.user_repo.get_by_email(request.email)
        if not user or not verify_password(request.password, user.password_hash or ""):
            raise ValueError("Invalid credentials")

        token = create_access_token(user.id)
        return user, token

    async def get_current_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return await self.user_repo.get_by_id(user_id)
    async def request_password_reset(self,email: str,):

        user = await self.user_repo.get_by_email(email)

        # Never reveal whether the account exists
        if not user:
            return

        # Remove previous reset links
        await self.reset_repo.delete_user_tokens(user.id)

        token = secrets.token_urlsafe(32)

        expires = datetime.utcnow() + timedelta(minutes=30)

        reset = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires,
        )

        await self.reset_repo.create(reset)

        reset_link = (
            f"{settings.FRONTEND_URL}/#/reset-password?token={token}"
        )

        await self.email_service.send_password_reset(
            email=user.email,
            first_name=user.first_name or "User",
            reset_link=reset_link,
        )
    # Later replace this with Resend/SendGrid
    async def reset_password(
                            self,
                            token: str,
                            new_password: str,
                        ):

        reset_token = await self.reset_repo.get_by_token(token)

        if not reset_token:
            raise ValueError("Invalid reset token.")

        if reset_token.expires_at < datetime.utcnow():
            raise ValueError("Reset token has expired.")

        user = await self.user_repo.get_by_id(
            reset_token.user_id
        )

        if not user:
            raise ValueError("User not found.")

        user.password_hash = hash_password(new_password)

        await self.session.commit()

        await self.reset_repo.delete(reset_token)


class UserService:
    """User service."""

    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)

    async def get_profile(self, user_id: str) -> Optional[User]:
        """Get user profile."""
        return await self.user_repo.get_by_id(user_id)

    async def update_profile(self, user_id: str, request: UserUpdate) -> Optional[User]:
        """Update user profile."""
        return await self.user_repo.update(
            user_id,
            first_name=request.first_name,
            last_name=request.last_name,
            image_url=request.image_url,
        )


class CompanyService:
    """Company service."""

    def __init__(self, session: AsyncSession):
        self.company_repo = CompanyRepository(session)

    async def get_all(self, skip: int = 0, limit: int = 100) -> Tuple[List[Company], int]:
        """Get all companies."""
        return await self.company_repo.get_all(skip, limit), await self.company_repo.count()

    async def get_by_id(self, company_id: str) -> Optional[Company]:
        """Get company by ID."""
        return await self.company_repo.get_by_id(company_id)

    async def search(
        self,
        search: Optional[str] = None,
        sector: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Company], int]:
        """Search companies."""
        return await self.company_repo.search(search or "", sector, skip, limit)

    


# Module-level cache: once legacy columns are dropped, skip ALTER TABLE on subsequent uploads
_embeddings_table_ready: bool = False


async def _ensure_embeddings_table(session: AsyncSession) -> None:
    """
    One-time setup: ensure pgvector extension + drop legacy JSON/vec columns.
    """
    global _embeddings_table_ready
    if _embeddings_table_ready:
        return
    try:
        await session.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.execute(sa_text(
            "ALTER TABLE embeddings DROP COLUMN IF EXISTS embedding"
        ))
        await session.execute(sa_text(
            "ALTER TABLE embeddings DROP COLUMN IF EXISTS vec"
        ))
        await session.commit()
    except Exception:
        await session.rollback()
        return
    _embeddings_table_ready = True


class DocumentService:
    """Document service."""

    def __init__(self, session: AsyncSession):
        self.doc_repo = DocumentRepository(session)
        self.s3 = S3Service()

    async def get_pending_documents(self, limit: int = 50) -> List[Document]:
        """Get documents that still need embeddings."""
        return await self.doc_repo.get_documents_without_chunks(limit=limit)

    async def process_pending_documents(self, limit: int = 50) -> int:
        """Process documents that do not have embeddings yet."""
        documents = await self.get_pending_documents(limit=limit)
        processed = 0
        for document in documents:
            try:
                success = await self.process_document_from_s3(document)
                if success:
                    processed += 1
            except Exception as exc:
                print(f"[documents] failed to process pending document {document.id}:", exc)
        return processed

    async def process_document_from_s3(self, document: Document) -> bool:
        """Download a stored document from S3 and generate embeddings."""
        if not document.file_url:
            print(f"[documents] skipping document {document.id} because file_url is missing")
            return False

        try:
            file_bytes = await self.s3.download_pdf(document.file_url)
        except Exception as exc:
            print(f"[documents] failed to download document {document.id} from S3:", exc)
            return False

        chunk_items, _ = self._extract_pdf_chunks(file_bytes)
        if not chunk_items:
            print(f"[documents] no text extracted for document {document.id}")
            return False

        return await self._process_document_embeddings(document, chunk_items)

    async def _process_document_embeddings(self, document: Document, chunk_items: List[tuple[str, int]]) -> bool:
        """
        Generate embeddings and store directly into the pgvector embedding_vector column.

        Creates RAGChunk rows for each chunk and Embedding rows with native
        pgvector Vector values (not JSON). No manual cosine similarity is needed
        at retrieval time — PostgreSQL handles it via the <=> operator.
        """
        if not chunk_items:
            print("[documents] no text extracted from PDF, skipping embedding creation")
            return False

        session = self.doc_repo.session

        # Ensure pgvector extension + drop legacy columns (one-time setup).
        # _ensure_embeddings_table has its own cached check, so this is a
        # fast no-op after the first successful run.
        await _ensure_embeddings_table(session)

        chunk_texts = [chunk_text for chunk_text, _ in chunk_items]

        # Generate embeddings via OpenAI
        embeddings = self._create_embeddings(chunk_texts)
        if not embeddings or len(embeddings) != len(chunk_items):
            print("[documents] embedding generation failed or returned wrong count")
            return False

        # Create RAGChunk + Embedding rows
        for (chunk_text, page_number), embedding_vector in zip(chunk_items, embeddings):
            rag_chunk = RAGChunk(
                document_id=document.id,
                company_id=document.company_id,
                page_number=page_number,
                chunk_text=chunk_text,
            )
            session.add(rag_chunk)
            # Flush to get the chunk ID
            await session.flush()

            embedding_obj = Embedding(
                chunk_id=rag_chunk.id,
                embedding_vector=embedding_vector,
            )
            session.add(embedding_obj)

        await session.commit()
        print(f"[documents] created {len(chunk_items)} RAG chunks + embeddings for document {document.id}")
        return True

    async def get_all(self, skip: int = 0, limit: int = 100) -> Tuple[List[Document], int]:
        """Get all documents."""
        return await self.doc_repo.get_all(skip, limit), await self.doc_repo.count()

    async def get_by_id(self, doc_id: str) -> Optional[Document]:
        """Get document by ID."""
        return await self.doc_repo.get_by_id(doc_id)

    async def get_by_company(self, company_id: str, skip: int = 0, limit: int = 100) -> Tuple[List[Document], int]:
        """Get documents by company."""
        return await self.doc_repo.get_by_company(company_id, skip, limit)

    async def search(self, search: str, skip: int = 0, limit: int = 100) -> Tuple[List[Document], int]:
        """Search documents."""
        return await self.doc_repo.search(search, skip, limit)

    async def filter_documents(
        self,
        skip: int,
        limit: int,
        search: Optional[str] = None,
        company_id: Optional[str] = None,
        report_type: Optional[str] = None,
        year: Optional[int] = None,
        quarter: Optional[str] = None,
    ) -> Tuple[List[Document], int]:
        """Filter documents by metadata."""
        return await self.doc_repo.filter_documents(
            skip=skip,
            limit=limit,
            search=search,
            company_id=company_id,
            report_type=report_type,
            year=year,
            quarter=quarter,
        )

    async def create(self, request: DocumentCreate) -> Document:
        """Create document."""
        doc = Document(
            id=f"doc_{uuid.uuid4().hex[:8]}",
            company_id=request.company_id,
            name=request.name,
            type=request.type,
            quarter=request.quarter,
            year=request.year,
            page_count=request.page_count,
            size_mb=request.size_mb,
            uploaded_at=datetime.utcnow(),
            file_url=request.file_url,
            source_url=request.source_url,
        )
        return await self.doc_repo.create(doc)

    async def update(self, doc_id: str, request: DocumentUpdate) -> Optional[Document]:
        """Update document."""
        return await self.doc_repo.update(doc_id, **request.dict(exclude_unset=True))

    async def delete(self, doc_id: str) -> bool:
        """Delete document."""
        return await self.doc_repo.delete(doc_id)

    async def upload_document(
        self,
        file: UploadFile,
        company_id: str,
        report_type: Optional[str] = None,
        year: Optional[int] = None,
        quarter: Optional[str] = None,
    ) -> Document:
        """Upload a document to S3, persist metadata, and create embeddings."""
        file_bytes = await file.read()
        file_url, size_mb = await self.s3.upload_pdf(
            contents=file_bytes,
            filename=file.filename,
            content_type=file.content_type,
            company_id=company_id,
        )

        chunks, page_count = self._extract_pdf_chunks(file_bytes)

        document = Document(
            id=f"doc_{uuid.uuid4().hex[:8]}",
            company_id=company_id,
            name=file.filename,
            type=report_type,
            quarter=quarter,
            year=year,
            page_count=page_count,
            size_mb=size_mb,
            uploaded_at=datetime.utcnow(),
            file_url=file_url,
            source_url=None,
        )

        print("[documents] persisting document to DB:", {
            "id": document.id,
            "company_id": document.company_id,
            "name": document.name,
            "type": document.type,
            "quarter": document.quarter,
            "year": document.year,
            "page_count": document.page_count,
            "size_mb": document.size_mb,
            "uploaded_at": document.uploaded_at,
            "file_url": document.file_url,
            "source_url": document.source_url,
        })

        created_document = await self.doc_repo.create(document)
        print("[documents] document persisted with id:", created_document.id)

        if chunks:
            await self._process_document_embeddings(created_document, chunks)

        return created_document

    def _extract_pdf_chunks(self, file_bytes: bytes) -> tuple[List[tuple[str, int]], Optional[int]]:
        try:
            reader = PdfReader(BytesIO(file_bytes))
        except Exception as exc:
            print("[documents] failed to read PDF:", exc)
            return [], None

        chunks: List[tuple[str, int]] = []
        page_count = len(reader.pages)
        for page_index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""

            if not text.strip():
                continue

            page_chunks = self._split_text(text)
            chunks.extend((chunk_text, page_index) for chunk_text in page_chunks)

        return chunks, page_count

    def _split_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return []

        chunks: List[str] = []
        start = 0
        while start < len(cleaned):
            end = min(start + chunk_size, len(cleaned))
            chunks.append(cleaned[start:end])
            start += chunk_size - overlap
        return chunks

    def _configure_embedding_client(self):
        if settings.OPENAI_API_KEY:
            print("[documents] using OpenAI")

            return OpenAI(
                api_key=settings.OPENAI_API_KEY,
            )

        if settings.OPENROUTER_API_KEY:
            print("[documents] using OpenRouter")

            return OpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
            )

        return None

    def _create_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a list of texts using OpenAI text-embedding-3-small.

        Returns a list of float vectors suitable for direct storage in
        a pgvector Vector column. No JSON serialization is involved.
        """
        client = self._configure_embedding_client()

        if client is None:
            return []

        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )

            return [item.embedding for item in response.data]

        except Exception as e:
            print("Embedding Error:", e)
            return []

class ConversationService:
    """Conversation service."""

    def __init__(self, session: AsyncSession):
        self.conv_repo = ConversationRepository(session)
        self.session = session

    async def get_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> Tuple[List[Conversation], int]:
        """Get conversations by user."""
        return await self.conv_repo.get_by_user(user_id, skip, limit)

    async def get_by_id(self, conv_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        return await self.conv_repo.get_by_id(conv_id)

    async def create(self, user_id: str, request: ConversationCreate) -> Conversation:
        """Create conversation."""
        conv = Conversation(
            id=f"conv_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            company_id=request.company_id,
            title=request.title or f"Conversation {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        )
        return await self.conv_repo.create(conv)

    async def update(self, conv_id: str, request: ConversationUpdate) -> Optional[Conversation]:
        """Update conversation."""
        return await self.conv_repo.update(conv_id, **request.dict(exclude_unset=True))

    async def delete(self, conv_id: str) -> bool:
        """Delete conversation."""
        return await self.conv_repo.delete(conv_id)


class MessageService:
    """Message service."""

    def __init__(self, session: AsyncSession):
        self.msg_repo = MessageRepository(session)
        self.conv_repo = ConversationRepository(session)
        self.source_repo = MessageSourceRepository(session)
        self.session = session

    async def get_by_conversation(self, conv_id: str) -> List[Message]:
        """Get all messages in conversation."""
        return await self.msg_repo.get_by_conversation(conv_id)

    async def get_by_id(self, msg_id: str) -> Optional[Message]:
        """Get message by ID."""
        return await self.msg_repo.get_by_id(msg_id)

    async def create(self, conv_id: str, request: MessageCreate) -> Message:
        """Create message."""
        msg = Message(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            conversation_id=conv_id,
            role=request.role,
            content=request.content,
            model=request.model,
        )
        created = await self.msg_repo.create(msg)

        # Update conversation message count
        conv = await self.conv_repo.get_by_id(conv_id)
        if conv:
            await self.conv_repo.update(conv_id, message_count=(conv.message_count or 0) + 1)

        return created

    async def delete(self, msg_id: str) -> bool:
        """Delete message."""
        return await self.msg_repo.delete(msg_id)


class BookmarkService:
    """Bookmark service."""

    def __init__(self, session: AsyncSession):
        self.bookmark_repo = BookmarkRepository(session)

    async def get_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> Tuple[List[Bookmark], int]:
        """Get bookmarks by user."""
        return await self.bookmark_repo.get_by_user(user_id, skip, limit)

    async def create(
        self,
        user_id: str,
        kind: str,
        ref_id: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
    ) -> Bookmark:
        """Create bookmark."""
        bookmark = Bookmark(
            id=f"bm_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            kind=kind,
            ref_id=ref_id,
            title=title,
            subtitle=subtitle,
        )
        return await self.bookmark_repo.create(bookmark)

    async def delete(self, bookmark_id: str) -> bool:
        """Delete bookmark."""
        return await self.bookmark_repo.delete(bookmark_id)


class AIInsightService:
    """AI Insight service."""

    def __init__(self, session: AsyncSession):
        self.insight_repo = AIInsightRepository(session)

    async def get_all(self, skip: int = 0, limit: int = 100) -> Tuple[List[AIInsight], int]:
        """Get all insights."""
        return await self.insight_repo.get_all(skip, limit), await self.insight_repo.count()

    async def get_by_company(self, company_id: str, skip: int = 0, limit: int = 100) -> Tuple[List[AIInsight], int]:
        """Get insights by company."""
        return await self.insight_repo.get_by_company(company_id, skip, limit)


class ChatService:
    """Chat service - handles AI interactions using RAG pipeline."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_service = ConversationService(session)
        self.msg_service = MessageService(session)

    async def chat(self, user_id: str, request: ChatRequest):
        """
        Process chat request using the production RAG pipeline.

        Orchestrates:
          1. RAG context retrieval (PGVector similarity search)
          2. Prompt building with financial assistant system prompt
          3. OpenRouter LLM call with fallback models
          4. Message persistence

        Returns:
            dict with conversation_id and content
        """
        from app.services.rag_service import run_rag_pipeline

        conversation_id, content, used_model = await run_rag_pipeline(
            session=self.session,
            user_id=user_id,
            message=request.message,
            model=request.model or "openai/gpt-4o",
            company_id=request.company_id,
            conversation_id=request.conversation_id,
        )

        return {
            "conversation_id": conversation_id,
            "content": content,
        }