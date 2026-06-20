"""
Documents Routes
GET /api/documents
GET /api/documents/{document_id}
GET /api/documents/company/{company_id}
POST /api/documents
PUT /api/documents/{document_id}
DELETE /api/documents/{document_id}
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.schemas import DocumentCreate, DocumentListResponse, DocumentResponse, DocumentUpdate
from app.services.services import DocumentService

router = APIRouter()


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List all documents with optional search."""
    service = DocumentService(session)
    skip = (page - 1) * limit

    if search:
        documents, total = await service.search(search, skip, limit)
    else:
        documents, total = await service.get_all(skip, limit)

    return DocumentListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[DocumentResponse.from_orm(d) for d in documents],
    )


@router.get("/{document_id}", response_model=dict)
async def get_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get document by ID."""
    service = DocumentService(session)
    document = await service.get_by_id(document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return {
        "success": True,
        "data": DocumentResponse.from_orm(document).dict(),
    }


@router.get("/company/{company_id}", response_model=DocumentListResponse)
async def get_company_documents(
    company_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Get documents by company ID."""
    service = DocumentService(session)
    skip = (page - 1) * limit
    documents, total = await service.get_by_company(company_id, skip, limit)

    return DocumentListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[DocumentResponse.from_orm(d) for d in documents],
    )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_document(
    request: DocumentCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new document."""
    service = DocumentService(session)
    document = await service.create(request)

    return {
        "success": True,
        "message": "Document created successfully",
        "data": DocumentResponse.from_orm(document).dict(),
    }


@router.put("/{document_id}", response_model=dict)
async def update_document(
    document_id: str,
    request: DocumentUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update a document."""
    service = DocumentService(session)
    document = await service.update(document_id, request)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return {
        "success": True,
        "message": "Document updated successfully",
        "data": DocumentResponse.from_orm(document).dict(),
    }


@router.delete("/{document_id}", response_model=dict)
async def delete_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete a document."""
    service = DocumentService(session)
    success = await service.delete(document_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return {
        "success": True,
        "message": "Document deleted successfully",
    }