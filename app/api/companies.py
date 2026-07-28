"""
Companies Routes
GET /api/companies
GET /api/companies/{company_id}
GET /api/companies/search
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.schemas import CompanyListResponse, CompanyResponse, PaginationParams,CompanyUpdate, CompanyCreate
from app.services.services import CompanyService

router = APIRouter()


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Get all companies with pagination."""
    service = CompanyService(session)
    skip = (page - 1) * limit
    companies, total = await service.get_all(skip, limit)

    print("[companies] list_companies called")
    print(f"[companies] total={total}, page={page}, limit={limit}")
    print(f"[companies] items={[(c.name if hasattr(c, 'name') else str(c)) for c in companies]}")

    return CompanyListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[CompanyResponse.from_orm(c) for c in companies],
    )


@router.get("/search", response_model=CompanyListResponse)
async def search_companies(
    search: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Search companies by name, sector, or industry."""
    service = CompanyService(session)
    skip = (page - 1) * limit
    companies, total = await service.search(search, sector, skip, limit)

    print("[companies] search_companies called")
    print(f"[companies] search={search}, sector={sector}, total={total}")
    print(f"[companies] items={[(c.name if hasattr(c, 'name') else str(c)) for c in companies]}")

    return CompanyListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[CompanyResponse.from_orm(c) for c in companies],
    )


@router.get("/{company_id}", response_model=dict)
async def get_company(
    company_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get company by ID."""
    service = CompanyService(session)
    company = await service.get_by_id(company_id)

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    return {
        "success": True,
        "data": CompanyResponse.from_orm(company).dict(),
    }
@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_company(
    request: CompanyCreate,
    session: AsyncSession = Depends(get_session),
):
    service = CompanyService(session)

    company = await service.create(request)

    return {
        "success": True,
        "message": "Company created successfully",
        "data": CompanyResponse.model_validate(company).model_dump(),
    }
@router.put("/{company_id}", response_model=dict)
async def update_company(
    company_id: str,
    request: CompanyUpdate,
    session: AsyncSession = Depends(get_session),
):
    service = CompanyService(session)

    company = await service.update(company_id, request)

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    return {
        "success": True,
        "message": "Company updated successfully",
        "data": CompanyResponse.model_validate(company).model_dump(),
    }
@router.delete("/{company_id}", response_model=dict)
async def delete_company(
    company_id: str,
    session: AsyncSession = Depends(get_session),
):
    service = CompanyService(session)

    deleted = await service.delete(company_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )

    return {
        "success": True,
        "message": "Company deleted successfully",
    }