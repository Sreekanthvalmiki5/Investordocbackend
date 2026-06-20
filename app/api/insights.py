"""
AI Insights Routes
GET /api/insights
GET /api/insights/company/{company_id}
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.schemas import AIInsightListResponse, AIInsightResponse
from app.services.services import AIInsightService

router = APIRouter()


@router.get("", response_model=AIInsightListResponse)
async def list_insights(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Get all AI insights with pagination."""
    service = AIInsightService(session)
    skip = (page - 1) * limit
    insights, total = await service.get_all(skip, limit)

    return AIInsightListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[AIInsightResponse.from_orm(i) for i in insights],
    )


@router.get("/company/{company_id}", response_model=AIInsightListResponse)
async def get_company_insights(
    company_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Get AI insights for a specific company."""
    service = AIInsightService(session)
    skip = (page - 1) * limit
    insights, total = await service.get_by_company(company_id, skip, limit)

    return AIInsightListResponse(
        success=True,
        page=page,
        limit=limit,
        total=total,
        items=[AIInsightResponse.from_orm(i) for i in insights],
    )