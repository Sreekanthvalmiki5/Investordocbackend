from typing import List, Optional, Dict, Any
import logging
import threading

# NOTE (memory optimization): heavy AI imports (langchain, langchain_huggingface,
# sentence-transformers, torch) are deliberately NOT imported at module level.
# Importing HuggingFaceEmbeddings here would pull torch + sentence-transformers
# into RAM for the entire process even though this deprecated service is never
# used by the app. They are imported lazily inside the methods that need them.

from app.core.config import settings


logger = logging.getLogger(__name__)

# Shared singleton embeddings instance: if this deprecated service is ever
# re-enabled, all VectorStoreService instances share ONE HuggingFaceEmbeddings
# object instead of each building their own model copy (~400 MB for
# all-MiniLM-L6-v2).
_shared_embeddings = None
_shared_embeddings_lock = threading.Lock()


class VectorStoreService:
    
    """
    DEPRECATED — This service is no longer used.

    The application now stores embeddings directly into the `embedding_vector`
    column (pgvector Vector type) on the `embeddings` table and performs
    similarity search via raw SQL using the <=> operator (see rag_service.py).

    This class relied on langchain_postgres (not installed) and
    HuggingFaceEmbeddings (384-dim), which is incompatible with the
    OpenAI text-embedding-3-small (1536-dim) embeddings used elsewhere.

    Kept for reference only. Will be removed in a future cleanup.
    """

    def __init__(self, connection_string: Optional[str] = None, embedding_model: Optional[str] = None):
        self.connection_string = connection_string or settings.VECTOR_DB_URL
        self.embedding_model =  (
    embedding_model or
    "sentence-transformers/all-MiniLM-L6-v2"
)
        # Lazy: the model is only loaded when an embedding is actually needed,
        # never during construction / module import.
        self._embeddings = None
        self._vectorstore = None

    def _get_embeddings(self):
        """Lazily load the shared HuggingFaceEmbeddings instance (once per process)."""
        global _shared_embeddings
        if _shared_embeddings is None:
            with _shared_embeddings_lock:
                if _shared_embeddings is None:
                    # Deferred import: torch / sentence-transformers are only
                    # loaded when a vector operation actually runs.
                    from langchain_huggingface import HuggingFaceEmbeddings

                    _shared_embeddings = HuggingFaceEmbeddings(
                        model_name=self.embedding_model
                    )
        self._embeddings = _shared_embeddings
        return self._embeddings

    def init_vectorstore(self, collection_name: str = "investordocs") -> None:
        if self._vectorstore is None:
            # Deferred import: langchain_postgres is only needed when the
            # vectorstore is actually used (this service is deprecated).
            try:
                from langchain_postgres import PGVector
            except Exception:
                PGVector = None

            if PGVector is None:
                raise RuntimeError("PGVector backend not available")

            self._vectorstore = PGVector(
                embeddings=self._get_embeddings(),
                connection=self.connection_string,
                collection_name=collection_name,
                use_jsonb=True,
            )
    def add_document_chunks(
        self,
        document_id: str,
        company_id: Optional[str],
        filename: str,
        report_type: Optional[str],
        year: Optional[int],
        quarter: Optional[str],
        chunks: List[tuple[str, int, int]],
        collection_name: str = "investordocs",
    ) -> None:
        """Add chunks to the vectorstore.

        chunks: list of (chunk_text, page_number, chunk_index)
        Metadata stored per chunk: document_id, company_id, filename, report_type, year, quarter, page_number, chunk_index
        """
        self.init_vectorstore(collection_name=collection_name)

        # Deferred import: langchain's Document class is small, but importing
        # langchain at module level would drag in a large dependency tree.
        from langchain.schema import Document as LCDocument

        docs = []
        for text, page_number, chunk_index in chunks:
            metadata: Dict[str, Any] = {
                "document_id": document_id,
                "company_id": company_id,
                "filename": filename,
                "report_type": report_type,
                "year": year,
                "quarter": quarter,
                "page_number": page_number,
                "chunk_index": chunk_index,
            }
            docs.append(LCDocument(page_content=text, metadata=metadata))

        # Add documents in batch to the vector store
        try:
            # Many PGVector implementations expose `add_documents` or `from_documents`.
           if hasattr(self._vectorstore, "add_documents"):
                self._vectorstore.add_documents(docs)
           elif hasattr(self._vectorstore, "from_documents"):
                self._vectorstore.from_documents(docs, embedding=self._embeddings)
           else:
                self._vectorstore = PGVector.from_documents(
                    documents=docs,
                    embedding=self._embeddings,
                    connection=self.connection_string,
                    collection_name=collection_name,
                )
        except Exception:
            logger.exception("Failed to add documents to PGVector")
            raise

    def similarity_search(self, query: str, k: int = 6, filter: Optional[dict] = None):
        self.init_vectorstore()
        self._get_embeddings()  # ensure shared model is loaded before use
        if hasattr(self._vectorstore, "similarity_search"):
            return self._vectorstore.similarity_search(query, k=k, filter=filter or {})
        # fallback
        if hasattr(self._vectorstore, "similarity_search_with_score"):
            return [d for d, _ in self._vectorstore.similarity_search_with_score(query, k=k, filter=filter or {})]
        raise RuntimeError("Vector store does not support similarity_search in this version")

    def get_retriever(self, search_kwargs: Optional[dict] = None):
        self.init_vectorstore()
        self._get_embeddings()  # ensure shared model is loaded before use
        if hasattr(self._vectorstore, "as_retriever"):
            return self._vectorstore.as_retriever(search_kwargs=search_kwargs or {"k": 6})
        # If not available, return a tiny wrapper that calls similarity_search
        class SimpleRetriever:
            def __init__(self, svc: VectorStoreService):
                self.svc = svc

            def get_relevant_documents(self, query: str):
                return self.svc.similarity_search(query, k=(search_kwargs or {}).get("k", 6))

        return SimpleRetriever(self)

    def delete_document(self, document_id: str):
        self.init_vectorstore()
        if hasattr(self._vectorstore, "delete"):
            return self._vectorstore.delete(document_id)
        # try SQL deletion via filter
        try:
            # some implementations expose a simple `delete` API, others require custom SQL.
            return False
        except Exception:
            logger.exception("Failed to delete document from vectorstore")
            return False
