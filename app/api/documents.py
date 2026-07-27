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

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, status, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.schemas import DocumentCreate, DocumentListResponse, DocumentResponse, DocumentUpdate
from app.services.services import DocumentService

router = APIRouter()



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


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),

    search: str | None = None,
    company_id: str | None = None,
    report_type: str | None = None,
    year: int | None = None,
    quarter: str | None = None,

    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session)

    skip = (page - 1) * limit

    documents, total = await service.filter_documents(
        skip=skip,
        limit=limit,
        search=search,
        company_id=company_id,
        report_type=report_type,
        year=year,
        quarter=quarter,
    )

    return DocumentListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[DocumentResponse.model_validate(d) for d in documents],
    )

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


@router.post("/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile | None = File(None),
    company_id: Optional[str] = Form(None),
    companyId: Optional[str] = Form(None),
    report_type: Optional[str] = Form(None),
    reportType: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    quarter: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    resolved_file = file
    resolved_company_id = (company_id or companyId or "unknown").strip()
    resolved_report_type = (report_type or reportType or "unknown").strip()

    if not resolved_file:
        try:
            form = await request.form()
        except Exception:
            form = None

        if form:
            print("[documents] upload form keys:", list(form.keys()))
            for key in ("file", "document", "upload", "pdf", "uploaded_file", "documentFile"):
                if key in form:
                    resolved_file = form[key]
                    break

            if not resolved_file:
                for value in form.values():
                    if hasattr(value, "filename"):
                        resolved_file = value
                        break

            resolved_company_id = (
                form.get("company_id")
                or form.get("companyId")
                or company_id
                or companyId
                or "unknown"
            ).strip()
            resolved_report_type = (
                form.get("report_type")
                or form.get("reportType")
                or report_type
                or reportType
                or "unknown"
            ).strip()
            if form.get("year") is not None:
                year = int(form.get("year")) if str(form.get("year")).isdigit() else None
            if form.get("quarter") is not None:
                quarter = str(form.get("quarter"))

    if not resolved_file:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A file is required",
        )

    print("[documents] upload_document called")
    print(f"[documents] company_id={resolved_company_id}, report_type={resolved_report_type}, year={year}, quarter={quarter}")

    service = DocumentService(session)

    try:
        document = await service.upload_document(
            file=resolved_file,
            company_id=resolved_company_id,
            report_type=resolved_report_type,
            year=year,
            quarter=quarter,
        )
    except Exception as exc:
        print("[documents] upload_document failed:", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    try:
        response_data = DocumentResponse.from_orm(document).model_dump()
    except Exception as exc:
        print("[documents] response serialization failed:", exc)
        response_data = {
            "id": document.id,
            "company_id": document.company_id,
            "name": document.name,
            "type": document.type,
            "quarter": document.quarter,
            "year": document.year,
            "page_count": document.page_coucnt,
            "size_mb": float(document.size_mb) if document.size_mb is not None else None,
            "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
            "file_url": document.file_url,
            "source_url": document.source_url,
            "starred": document.starred,
        }

    print("[documents] upload response_data=", response_data)
    return {
        "success": True,
        "data": response_data,
    }


@router.post("/scheduler/run", response_model=dict)
async def run_embedding_scheduler(
    session: AsyncSession = Depends(get_session),
):
    """Run pending document embedding creation immediately."""
    service = DocumentService(session)
    processed = await service.process_pending_documents(limit=100)
    return {
        "success": True,
        "message": f"Processed {processed} pending documents.",
        "processed": processed,
    }