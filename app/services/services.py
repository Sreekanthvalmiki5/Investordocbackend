"""
Service Layer
Business logic layer with repository injection.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insight import AIInsight
from app.models.bookmark import  Bookmark
from app.models.company import Company
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.models.message import MessageSource
from app.models.user import  User

from app.repositories.repositories import (
    AIInsightRepository,
    BookmarkRepository,
    CompanyRepository,
    ConversationRepository,
    DocumentRepository,
    MessageRepository,
    MessageSourceRepository,
    UserRepository,
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
)
from app.core.security import create_access_token, hash_password, verify_password


class AuthService:
    """Authentication service."""

    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)
        self.session = session

    async def register(self, request: RegisterRequest) -> User:
        """Register a new user."""
        # Check if user exists
        existing = await self.user_repo.get_by_email(request.email)
        if existing:
            raise ValueError("User already exists")

        # Create user
        user = User(
            id=str(uuid.uuid4()),
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


class DocumentService:
    """Document service."""

    def __init__(self, session: AsyncSession):
        self.doc_repo = DocumentRepository(session)

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
    """Chat service - handles AI interactions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_service = ConversationService(session)
        self.msg_service = MessageService(session)

    async def chat(self, user_id: str, request: ChatRequest) -> Message:
        """
        Process chat request.
        Currently returns mocked responses.
        Future: Replace with OpenAI/Claude/DeepSeek + RAG.
        """
        # Get or create conversation
        conv_id = request.conversation_id
        if not conv_id:
            conv = await self.conv_service.create(
                user_id,
                ConversationCreate(
                    title=request.message[:50],
                    company_id=request.company_id,
                ),
            )
            conv_id = conv.id

        # Store user message
        user_msg = await self.msg_service.create(
            conv_id,
            MessageCreate(
                role="user",
                content=request.message,
                model=request.model,
            ),
        )

        # Generate mocked assistant response
        assistant_response = self._generate_mock_response(request)

        # Store assistant message
        assistant_msg = await self.msg_service.create(
            conv_id,
            MessageCreate(
                role="assistant",
                content=assistant_response,
                model=request.model,
            ),
        )

        return assistant_msg

    def _generate_mock_response(self, request: ChatRequest) -> str:
        """Generate mock AI response for now."""
        company = request.company_id or "the company"
        
        # Mock responses based on keywords
        if "quarterly results" in request.message.lower() or "results" in request.message.lower():
            return f"Based on the latest filings for {company}, the quarterly results show strong performance with consistent revenue growth. The net profit margin improved by 2.3% compared to the previous quarter, driven by operational efficiency improvements and market expansion."
        
        elif "risk" in request.message.lower():
            return f"Key risks identified for {company} include: 1) Market volatility and competitive pressures, 2) Regulatory changes in key markets, 3) Supply chain disruptions, and 4) Currency fluctuations. These are typical industry risks that the company actively monitors and mitigates."
        
        elif "growth" in request.message.lower() or "expansion" in request.message.lower():
            return f"{company} demonstrates strong growth drivers including: 1) Expansion into emerging markets, 2) Digital transformation initiatives, 3) Product portfolio diversification, and 4) Strategic partnerships. Year-over-year growth is projected at 15-20% for the next fiscal year."
        
        elif "management" in request.message.lower() or "commentary" in request.message.lower():
            return f"Management commentary indicates confidence in the company's strategic direction. The leadership team emphasizes focus on innovation, operational excellence, and customer satisfaction. They believe current market conditions present significant opportunities for growth and market share expansion."
        
        elif "bullish" in request.message.lower() or "positive" in request.message.lower():
            return f"Bullish signals for {company}: Strong cash flow generation, improving margins, market leadership position, and successful new product launches. Analyst consensus shows a 'buy' rating with price target upside of 25-30% over the next 12 months."
        
        elif "bearish" in request.message.lower() or "negative" in request.message.lower():
            return f"Some bearish indicators include: Increased competition in core markets, rising input costs, and margin compression in certain segments. However, management's strategic initiatives are expected to address these challenges over the medium term."
        
        elif "profit" in request.message.lower() or "revenue" in request.message.lower():
            return f"Revenue for {company} reached $5.2B in the latest quarter, representing 8% YoY growth. Net profit margin is 18%, with EBITDA of $1.1B. Strong profitability is supported by operational efficiency and pricing power in key markets."
        
        else:
            return f"Based on the available financial documents and filings for {company}, I can provide comprehensive analysis of their financial metrics, risks, growth prospects, and management outlook. Please feel free to ask specific questions about revenue, profitability, market position, or any other aspect of the company's performance."