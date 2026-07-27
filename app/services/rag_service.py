"""
RAG Service
Production-grade Retrieval-Augmented Generation pipeline using PGVector and OpenRouter.

Architecture:
  1. retrieve_context()   → PGVector similarity search via SQL (<=> operator)
  2. build_prompt()       → Format context + system prompt
  3. generate_answer()    → OpenRouter LLM call with fallback models
  4. save_messages()      → Persist user + assistant messages with sources
  5. return_response()    → Return structured response

Vector storage: Uses the `embedding_vector` column (pgvector Vector type) on the
`embeddings` table. No JSON embeddings are ever created or read.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level cache for vector extension (checked once, then cached)
_vector_extension_ready: bool = False

# ============================================================================
# Constants
# ============================================================================

SYSTEM_PROMPT = (
    "You are an AI financial assistant.\n\n"
    "Answer ONLY using the provided context.\n\n"
    "If the answer is not present in the context, reply:\n"
    "'I could not find this information in the uploaded documents.'\n\n"
    "Never invent facts.\n\n"
    "Generate a complete professional answer in Markdown."
)

# Primary model (fast, reliable, no reasoning overhead)
# Uses :free suffix for OpenRouter free tier (rate-limited but zero cost)
# Model must NOT require mandatory reasoning (excludes o-series models)
PRIMARY_MODEL = "gemma-4-26b-a4b-it:free"

FALLBACK_MODELS = [
    "google/gemma-4-31b",
    "openrouter/free",
]
SIMILARITY_THRESHOLD = 0.45
TOP_K = 8
MAX_TOKENS = 512
MAX_CONTEXT_CHARS = 12000  # Trim context to avoid exceeding model context window


# ============================================================================
# 1. Embedding Generation
# ============================================================================

def _get_embedding_client() -> Optional[OpenAI]:
    """
    Configure and return an OpenAI-compatible client for generating embeddings.

    Priority:
    1. OpenAI API key (direct)
    2. OpenRouter API key (via OpenRouter's /v1/embeddings endpoint)
    """
    if settings.OPENAI_API_KEY:
        logger.info("Using OpenAI for embeddings")
        return OpenAI(api_key=settings.OPENAI_API_KEY)

    if settings.OPENROUTER_API_KEY:
        logger.info("Using OpenRouter for embeddings")
        return OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )

    logger.error("No API key configured for embeddings (set OPENAI_API_KEY or OPENROUTER_API_KEY)")
    return None


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding vector using text-embedding-3-small (via OpenAI or OpenRouter)."""
    client = _get_embedding_client()
    if client is None:
        return None

    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.error("Failed to generate embedding: %s", exc)
        return None


# ============================================================================
# 2. Database Setup (Run Once)
# ============================================================================

async def _ensure_vector_extension(session: AsyncSession) -> None:
    """
    Ensure pgvector extension exists and the embeddings table is ready.

    On first call:
    - Creates the vector extension if missing
    - Ensures the embedding_vector column is populated from legacy columns
    - Creates an HNSW index for fast similarity search
    - Caches readiness to avoid repeated checks

    Called once per process lifetime. Subsequent calls are no-ops.
    """
    global _vector_extension_ready
    if _vector_extension_ready:
        return

    try:
        # 1. Enable the pgvector extension
        await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.commit()

        # 2. Backfill embedding_vector from legacy vec column (safe no-op if column missing)
        try:
            await session.execute(
                text(
                    "UPDATE embeddings SET embedding_vector = vec "
                    "WHERE embedding_vector IS NULL AND vec IS NOT NULL"
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.info("Legacy `vec` column not found — skipping backfill from vec")

        # 3. Backfill embedding_vector from legacy JSON embedding column (safe no-op if column missing)
        try:
            await session.execute(
                text(
                    "UPDATE embeddings SET embedding_vector = embedding::text::vector "
                    "WHERE embedding_vector IS NULL AND embedding IS NOT NULL"
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.info("Legacy `embedding` (JSON) column not found — skipping backfill from JSON")

        # 4. Create HNSW index for fast approximate nearest neighbour search
        await session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx "
                "ON embeddings "
                "USING hnsw (embedding_vector vector_cosine_ops)"
            )
        )
        await session.commit()

        # 5. Drop legacy columns after successful backfill
        try:
            await session.execute(text(
                "ALTER TABLE embeddings DROP COLUMN IF EXISTS embedding"
            ))
            await session.execute(text(
                "ALTER TABLE embeddings DROP COLUMN IF EXISTS vec"
            ))
            await session.commit()
            logger.info("Dropped legacy `embedding` (JSON) and `vec` columns")
        except Exception:
            await session.rollback()
            logger.info("Could not drop legacy columns (may not exist on fresh database)")

        _vector_extension_ready = True
        logger.info("PGVector extension, backfill, column cleanup, and HNSW index ready")

    except Exception as exc:
        logger.warning("PGVector setup failed (will retry on next call): %s", exc)
        await session.rollback()


# ============================================================================
# 3. Context Retrieval (PGVector Native Similarity Search)
# ============================================================================

async def retrieve_context(
    session: AsyncSession,
    query_embedding: List[float],
    company_id: Optional[str] = None,
    top_k: int = TOP_K,
    min_score: float = SIMILARITY_THRESHOLD,
) -> Tuple[List[Dict[str, Any]], List[float]]:
    """
    Retrieve top-k relevant chunks using native PGVector similarity search.

    Uses the pgvector <=> (cosine distance) operator on the
    embedding_vector column. Never loads embeddings into Python memory.

    Args:
        session: DB session
        query_embedding: Float vector from embedding model
        company_id: Optional company filter
        top_k: Maximum chunks to return
        min_score: Minimum similarity threshold (0.0 to 1.0)

    Returns:
        Tuple of (chunks list, scores list)
        Each chunk dict contains chunk_id, document_id, page_number,
        chunk_text, filename, report_type, year, quarter, similarity_score
    """
    await _ensure_vector_extension(session)

    query_vec_str = str(query_embedding)

    # Use CAST(... AS vector) instead of ::vector suffix because
    # SQLAlchemy's text() doesn't parse :param::type correctly when
    # used with the asyncpg driver (which uses $1 positional params).
    sql = """
        SELECT
            rc.id AS chunk_id,
            rc.document_id,
            rc.company_id,
            rc.page_number,
            rc.chunk_text,
            rc.created_at,
            d.name AS filename,
            d.type AS report_type,
            d.year,
            d.quarter,
            1 - (e.embedding_vector <=> CAST(:query_vec AS vector)) AS similarity_score
        FROM rag_chunks rc
        JOIN embeddings e ON e.chunk_id = rc.id
        LEFT JOIN documents d ON d.id = rc.document_id
        WHERE 1 - (e.embedding_vector <=> CAST(:query_vec AS vector)) >= :min_score
    """
    params: Dict[str, Any] = {
        "query_vec": query_vec_str,
        "min_score": min_score,
        "top_k": top_k,
    }

    if company_id:
        sql += " AND rc.company_id = :company_id"
        params["company_id"] = company_id

    sql += """
        ORDER BY e.embedding_vector <=> CAST(:query_vec AS vector)
        LIMIT :top_k
    """

    result = await session.execute(text(sql), params)
    rows = result.fetchall()

    chunks: List[Dict[str, Any]] = []
    scores: List[float] = []
    seen_texts: set = set()

    for row in rows:
        row_dict = dict(row._mapping)

        # Deduplicate near-identical chunks
        text_preview = row_dict["chunk_text"][:200] if row_dict["chunk_text"] else ""
        text_key = text_preview.strip().lower()
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        score = float(row_dict["similarity_score"])
        chunks.append(row_dict)
        scores.append(score)

        logger.info(
            "Retrieved chunk %s (doc=%s, page=%s, score=%.4f)",
            row_dict["chunk_id"],
            row_dict["document_id"],
            row_dict["page_number"],
            score,
        )

    logger.info(
        "Retrieved %d unique chunks (requested top_k=%d, min_score=%.2f)",
        len(chunks), top_k, min_score,
    )

    return chunks, scores


# ============================================================================
# 4. Prompt Building
# ============================================================================

def build_prompt(
    user_question: str,
    chunks: List[Dict[str, Any]],
) -> Tuple[str, str, List[Dict[str, str]]]:
    """
    Build system prompt + user message with context.

    Returns:
        Tuple of (system_prompt, formatted_user_message, messages_list)
    """
    if not chunks:
        no_context_msg = (
            f"Question: {user_question}\n\n"
            "Context:\n"
            "No relevant documents found.\n\n"
            "Please inform the user that no relevant information was found."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": no_context_msg},
        ]
        return SYSTEM_PROMPT, no_context_msg, messages

    # Build formatted context with Document 1 / Document 2 / ... headers
    context_parts: List[str] = []
    context_parts.append("Context:")
    context_parts.append("")

    total_chars = 0
    for i, chunk in enumerate(chunks, 1):
        doc_label = chunk.get("filename") or f"Document {chunk.get('document_id', 'unknown')}"
        page_info = f" (Page {chunk['page_number']})" if chunk.get("page_number") else ""
        score_info = f" [Score: {chunk.get('similarity_score', 0):.3f}]"

        header = f"Document {i}: {doc_label}{page_info}{score_info}"
        text = chunk.get("chunk_text", "").strip()

        entry = f"{header}\n{text}\n"

        if total_chars + len(entry) > MAX_CONTEXT_CHARS:
            remaining_budget = MAX_CONTEXT_CHARS - total_chars
            if remaining_budget > 100:
                entry = entry[:remaining_budget] + "\n[Context truncated...]"
                context_parts.append(entry)
            else:
                context_parts.append("--- Context continues but was truncated ---")
            break

        context_parts.append(entry)
        total_chars += len(entry)

    context_str = "\n".join(context_parts)
    user_message = f"Question: {user_question}\n\n{context_str}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    prompt_total = sum(len(m["content"]) for m in messages)
    logger.info("Built prompt: %d characters, %d chunks in context", prompt_total, len(chunks))

    return SYSTEM_PROMPT, user_message, messages


# ============================================================================
# 5. OpenRouter LLM Call
# ============================================================================

async def call_openrouter(
    messages: List[Dict[str, str]],
    model: str,
    max_tokens: int = MAX_TOKENS,
    temperature: float = 0.1,
) -> str:
    """
    Call OpenRouter chat completions API with fallback support.

    Handles:
    - content (normal response)
    - reasoning (thinking tokens with no visible content)
    - finish_reason (length, stop, etc.)
    - max_output_tokens (reasoning used all budget)
    - API errors

    Returns:
        Generated answer text. Never returns empty string.
    """
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        logger.error("OPENROUTER_API_KEY is not configured")
        return _fallback_response()

    base_url = settings.OPENROUTER_API_BASE.rstrip("/")
    url = f"{base_url}/chat/completions"

    # Try models in sequence until one returns content
    models_to_try = list(dict.fromkeys([model] + FALLBACK_MODELS))

    for attempt, try_model in enumerate(models_to_try):
        if attempt > 0:
            logger.info("Falling back to model: %s", try_model)

        payload: Dict[str, Any] = {
            "model": try_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://investordocs.ai",
            "X-Title": "InvestorDocs AI",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 429:
                logger.warning("Rate limited on model %s, trying next", try_model)
                continue

            resp.raise_for_status()
            j = resp.json()

            # Log token usage
            usage = j.get("usage", {})
            if usage:
                logger.info(
                    "Token usage - model=%s prompt=%d completion=%d total=%d",
                    try_model,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    usage.get("total_tokens", 0),
                )

            choices = j.get("choices", [])
            if not choices:
                logger.warning("No choices in response for model %s", try_model)
                continue

            choice = choices[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")
            native_finish = choice.get("native_finish_reason", "")

            content = message.get("content")
            reasoning = message.get("reasoning")
            has_reasoning = reasoning is not None and reasoning != ""
            logger.info("Message object:\n%s", message)

            logger.info("Content:\n%s", message.get("content"))

            logger.info("Reasoning:\n%s", message.get("reasoning"))

            logger.info("Finish reason: %s", choice.get("finish_reason"))

            logger.info("Native finish: %s", choice.get("native_finish_reason"))

            logger.info(
                "Response - model=%s finish_reason=%s native_finish=%s "
                "has_content=%s has_reasoning=%s",
                try_model, finish_reason, native_finish,
                bool(content), has_reasoning,
            )

            # If reasoning consumed all tokens, retry with larger budget
            if not content and has_reasoning and finish_reason in ("length",):
                logger.warning(
                    "Model %s used all tokens on reasoning, trying next fallback",
                    try_model,
                )
                max_tokens = min(max_tokens * 2, 8192)
                continue

            if content and isinstance(content, str) and content.strip():
                logger.info(
                    "Successfully generated response with model %s (finish_reason=%s)",
                    try_model, finish_reason,
                )
                return content.strip()

            logger.warning(
                "Empty content from model %s (finish=%s, native=%s)",
                try_model, finish_reason, native_finish,
            )

        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error with model %s: %s - %s",
                try_model, exc.response.status_code, exc.response.text[:500],
            )
            continue
        except httpx.TimeoutException:
            logger.error("Timeout with model %s", try_model)
            continue
        except Exception as exc:
            logger.exception("Unexpected error with model %s: %s", try_model, exc)
            continue

    logger.error("All models failed to generate a response")
    return _fallback_response()


def _fallback_response() -> str:
    """Return a safe fallback when the LLM fails."""
    return (
        "I apologize, but I'm unable to process your request at the moment. "
        "The AI service is temporarily unavailable. Please try again later."
    )


# ============================================================================
# 6. Save Messages to Database
# ============================================================================

async def save_messages(
    session: AsyncSession,
    conversation_id: str,
    user_message: str,
    assistant_content: str,
    model: str,
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Any, Any]:
    """
    Save user and assistant messages to the database.
    Creates MessageSource entries for citations.

    Returns:
        Tuple of (user_msg_obj, assistant_msg_obj)
    """
    from app.models.message import Message, MessageSource
    from app.repositories.repositories import ConversationRepository

    conv_repo = ConversationRepository(session)

    user_msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    assistant_msg_id = f"msg_{uuid.uuid4().hex[:12]}"

    user_msg = Message(
        id=user_msg_id,
        conversation_id=conversation_id,
        role="user",
        content=user_message,
        model=model,
    )
    session.add(user_msg)

    assistant_msg = Message(
        id=assistant_msg_id,
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        model=model,
    )
    session.add(assistant_msg)

    if chunks:
        for chunk in chunks:
            source = MessageSource(
                id=f"src_{uuid.uuid4().hex[:12]}",
                message_id=assistant_msg_id,
                document_id=chunk.get("document_id"),
                title=chunk.get("filename"),
                page=chunk.get("page_number"),
            )
            session.add(source)

    conv = await conv_repo.get_by_id(conversation_id)
    if conv:
        await conv_repo.update(conversation_id, message_count=(conv.message_count or 0) + 2)

    await session.commit()
    await session.refresh(user_msg)
    await session.refresh(assistant_msg)

    logger.info(
        "Saved user msg=%s and assistant msg=%s to conversation %s",
        user_msg_id, assistant_msg_id, conversation_id,
    )

    return user_msg, assistant_msg


# ============================================================================
# 7. Response Formatting
# ============================================================================

def format_answer(answer: str, chunks: List[Dict[str, Any]]) -> str:
    """Enhance the answer with citations and proper Markdown formatting."""
    if not chunks:
        return answer

    not_found_indicators = [
        "could not find this information",
        "could not find relevant information",
        "not present in the context",
        "no relevant information was found",
        "no relevant documents found",
    ]
    is_not_found = any(indicator in answer.lower() for indicator in not_found_indicators)
    has_citations = "**Sources:**" in answer or "*Sources:*" in answer

    if not is_not_found and not has_citations and chunks:
        seen_docs: set = set()
        sources: List[str] = []
        for chunk in chunks:
            doc_id = chunk.get("document_id", "")
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)

            doc_label = chunk.get("filename") or f"Document {doc_id[:12]}"
            page = chunk.get("page_number")
            if page:
                sources.append(f"- {doc_label} (Page {page})")
            else:
                sources.append(f"- {doc_label}")

        if sources:
            answer += "\n\n---\n\n**Sources:**\n" + "\n".join(sources)

    return answer


# ============================================================================
# 8. Orchestrator
# ============================================================================

async def run_rag_pipeline(
    session: AsyncSession,
    user_id: str,
    message: str,
    model: str,
    company_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Execute the full RAG pipeline end-to-end.

    Args:
        session: DB session
        user_id: Current user ID
        message: User's question
        model: Requested LLM model
        company_id: Optional company filter
        conversation_id: Optional existing conversation ID

    Returns:
        Tuple of (conversation_id, assistant_content, used_model)
    """
    from app.schemas.schemas import ConversationCreate
    from app.services.services import ConversationService

    conv_service = ConversationService(session)

    # Step 1: Ensure we have a conversation
    if not conversation_id:
        conv = await conv_service.create(
            user_id,
            ConversationCreate(
                title=message[:80],
                company_id=company_id,
            ),
        )
        conversation_id = conv.id
        logger.info("Created new conversation %s", conversation_id)

    # Step 2: Generate query embedding
    logger.info("Generating embedding for query (len=%d chars)", len(message))
    query_embedding = generate_embedding(message)
    if not query_embedding:
        logger.error("Failed to generate query embedding")
        assistant_content = (
            "I apologize, but I encountered an error processing your question. "
            "Please try again later."
        )
        await save_messages(session, conversation_id, message, assistant_content, model)
        return conversation_id, assistant_content, model

    # Step 3: Retrieve context using PGVector (native similarity search)
    logger.info("Retrieving context (company_id=%s)", company_id or "all")
    chunks, scores = await retrieve_context(
        session=session,
        query_embedding=query_embedding,
        company_id=company_id,
    )

    if scores:
        logger.info(
            "Retrieval scores - min=%.4f max=%.4f avg=%.4f",
            min(scores), max(scores), sum(scores) / len(scores),
        )
    else:
        logger.info("No relevant chunks found above threshold %.2f", SIMILARITY_THRESHOLD)

    # Step 4: Build prompt
    system_prompt, user_msg_with_context, messages = build_prompt(message, chunks)
    prompt_chars = sum(len(m["content"]) for m in messages)
    logger.info("Prompt length: %d characters across %d messages", prompt_chars, len(messages))

    # Step 5: Generate answer via OpenRouter
    used_model = model if model in [PRIMARY_MODEL] + FALLBACK_MODELS else PRIMARY_MODEL
    answer = await call_openrouter(messages, used_model)

    # If no context was found and answer doesn't mention it, prepend notice
    if not chunks and "could not find" not in answer.lower():
        answer = (
            "I could not find relevant information in the uploaded documents.\n\n"
            f"{answer}"
        )

    # Step 6: Format answer with citations
    formatted_answer = format_answer(answer, chunks)

    # Step 7: Save messages with sources
    await save_messages(session, conversation_id, message, formatted_answer, used_model, chunks)

    logger.info(
        "RAG pipeline complete - conv=%s model=%s answer_len=%d chunks=%d",
        conversation_id, used_model, len(formatted_answer), len(chunks),
    )

    return conversation_id, formatted_answer, used_model
