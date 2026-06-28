"""
Repository Layer
Data access layer with SQLAlchemy async queries.
"""

from typing import List, Optional, Tuple

from sqlalchemy import select,delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.bookmark import Bookmark
from app.models.company import Company
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.insight import AIInsight
from app.models.message import Message, MessageSource
from app.models.user import User


from app.models.password_reset import PasswordResetToken



class UserRepository:
    """Repository for User model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Create a new user."""
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user_id: str, **kwargs) -> Optional[User]:
        """Update user fields."""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user_id: str) -> bool:
        """Delete a user."""
        user = await self.get_by_id(user_id)
        if not user:
            return False
        await self.session.delete(user)
        await self.session.commit()
        return True


class CompanyRepository:
    """Repository for Company model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, company_id: str) -> Optional[Company]:
        """Get company by ID."""
        stmt = select(Company).where(Company.id == company_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Company]:
        """Get all companies with pagination."""
        stmt = select(Company).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Get total count of companies."""
        stmt = select(func.count(Company.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def search(
        self,
        search: str,
        sector: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[Company], int]:
        """Search companies by name, ticker, or industry, with optional sector filter."""
        stmt = select(Company)

        if search:
            search_filter = or_(
                Company.name.ilike(f"%{search}%"),
                Company.ticker.ilike(f"%{search}%"),
                Company.industry.ilike(f"%{search}%"),
            )
            stmt = stmt.where(search_filter)

        if sector:
            stmt = stmt.where(Company.sector == sector)

        # Count total matching results
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch paginated results
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create(self, company: Company) -> Company:
        """Create a new company."""
        self.session.add(company)
        await self.session.commit()
        await self.session.refresh(company)
        return company

    async def update(self, company_id: str, **kwargs) -> Optional[Company]:
        """Update company fields."""
        company = await self.get_by_id(company_id)
        if not company:
            return None
        for key, value in kwargs.items():
            if hasattr(company, key):
                setattr(company, key, value)
        await self.session.commit()
        await self.session.refresh(company)
        return company

    async def delete(self, company_id: str) -> bool:
        """Delete a company."""
        company = await self.get_by_id(company_id)
        if not company:
            return False
        await self.session.delete(company)
        await self.session.commit()
        return True


class DocumentRepository:
    """Repository for Document model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, doc_id: str) -> Optional[Document]:
        """Get document by ID."""
        stmt = select(Document).where(Document.id == doc_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get all documents with pagination."""
        stmt = select(Document).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Get total count of documents."""
        stmt = select(func.count(Document.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_by_company(
        self, company_id: str, skip: int = 0, limit: int = 100
    ) -> Tuple[List[Document], int]:
        """Get documents by company ID with pagination."""
        stmt = select(Document).where(Document.company_id == company_id)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def search(
        self, search: str, skip: int = 0, limit: int = 100
    ) -> Tuple[List[Document], int]:
        """Search documents by name."""
        stmt = select(Document).where(
            Document.name.ilike(f"%{search}%")
        )

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create(self, document: Document) -> Document:
        """Create a new document."""
        self.session.add(document)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def update(self, doc_id: str, **kwargs) -> Optional[Document]:
        """Update document fields."""
        document = await self.get_by_id(doc_id)
        if not document:
            return None
        for key, value in kwargs.items():
            if hasattr(document, key):
                setattr(document, key, value)
        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        document = await self.get_by_id(doc_id)
        if not document:
            return False
        await self.session.delete(document)
        await self.session.commit()
        return True


class ConversationRepository:
    """Repository for Conversation model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, conv_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        stmt = select(Conversation).where(Conversation.id == conv_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user(
        self, user_id: str, skip: int = 0, limit: int = 100
    ) -> Tuple[List[Conversation], int]:
        """Get conversations by user ID with pagination."""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
        )

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def update(self, conv_id: str, **kwargs) -> Optional[Conversation]:
        """Update conversation fields."""
        conversation = await self.get_by_id(conv_id)
        if not conversation:
            return None
        for key, value in kwargs.items():
            if hasattr(conversation, key):
                setattr(conversation, key, value)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def delete(self, conv_id: str) -> bool:
        """Delete a conversation."""
        conversation = await self.get_by_id(conv_id)
        if not conversation:
            return False
        await self.session.delete(conversation)
        await self.session.commit()
        return True


class MessageRepository:
    """Repository for Message model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, msg_id: str) -> Optional[Message]:
        """Get message by ID."""
        stmt = select(Message).where(Message.id == msg_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_conversation(self, conv_id: str) -> List[Message]:
        """Get all messages in a conversation, ordered by creation time."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, message: Message) -> Message:
        """Create a new message."""
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def delete(self, msg_id: str) -> bool:
        """Delete a message."""
        message = await self.get_by_id(msg_id)
        if not message:
            return False
        await self.session.delete(message)
        await self.session.commit()
        return True


class MessageSourceRepository:
    """Repository for MessageSource model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, source_id: str) -> Optional[MessageSource]:
        """Get message source by ID."""
        stmt = select(MessageSource).where(MessageSource.id == source_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_message(self, message_id: str) -> List[MessageSource]:
        """Get all sources for a message."""
        stmt = select(MessageSource).where(MessageSource.message_id == message_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, source: MessageSource) -> MessageSource:
        """Create a new message source."""
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def delete(self, source_id: str) -> bool:
        """Delete a message source."""
        source = await self.get_by_id(source_id)
        if not source:
            return False
        await self.session.delete(source)
        await self.session.commit()
        return True


class BookmarkRepository:
    """Repository for Bookmark model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(
        self, user_id: str, skip: int = 0, limit: int = 100
    ) -> Tuple[List[Bookmark], int]:
        """Get bookmarks by user ID with pagination."""
        stmt = (
            select(Bookmark)
            .where(Bookmark.user_id == user_id)
            .order_by(Bookmark.created_at.desc())
        )

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create(self, bookmark: Bookmark) -> Bookmark:
        """Create a new bookmark."""
        self.session.add(bookmark)
        await self.session.commit()
        await self.session.refresh(bookmark)
        return bookmark

    async def delete(self, bookmark_id: str) -> bool:
        """Delete a bookmark."""
        bookmark = await self.get_by_id(bookmark_id)
        if not bookmark:
            return False
        await self.session.delete(bookmark)
        await self.session.commit()
        return True

    async def get_by_id(self, bookmark_id: str) -> Optional[Bookmark]:
        """Get bookmark by ID."""
        stmt = select(Bookmark).where(Bookmark.id == bookmark_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class AIInsightRepository:
    """Repository for AIInsight model."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[AIInsight]:
        """Get all insights with pagination."""
        stmt = select(AIInsight).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Get total count of insights."""
        stmt = select(func.count(AIInsight.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_by_company(
        self, company_id: str, skip: int = 0, limit: int = 100
    ) -> Tuple[List[AIInsight], int]:
        """Get insights by company ID with pagination."""
        stmt = select(AIInsight).where(AIInsight.company_id == company_id)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create(self, insight: AIInsight) -> AIInsight:
        """Create a new insight."""
        self.session.add(insight)
        await self.session.commit()
        await self.session.refresh(insight)
        return insight

    async def update(self, insight_id: str, **kwargs) -> Optional[AIInsight]:
        """Update insight fields."""
        insight = await self.get_by_id(insight_id)
        if not insight:
            return None
        for key, value in kwargs.items():
            if hasattr(insight, key):
                setattr(insight, key, value)
        await self.session.commit()
        await self.session.refresh(insight)
        return insight

    async def delete(self, insight_id: str) -> bool:
        """Delete an insight."""
        insight = await self.get_by_id(insight_id)
        if not insight:
            return False
        await self.session.delete(insight)
        await self.session.commit()
        return True

    async def get_by_id(self, insight_id: str) -> Optional[AIInsight]:
        """Get insight by ID."""
        stmt = select(AIInsight).where(AIInsight.id == insight_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
class PasswordResetRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, token: PasswordResetToken):
        self.session.add(token)
        await self.session.commit()
        await self.session.refresh(token)
        return token

    async def get_by_token(self, token: str):
        
        result = await self.session.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token == token)
        )
        return result.scalar_one_or_none()

    async def delete(self, token: PasswordResetToken):
        await self.session.delete(token)
        await self.session.commit()

    async def delete_user_tokens(self, user_id):
        await self.session.execute(
            delete(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
        )
        await self.session.commit()