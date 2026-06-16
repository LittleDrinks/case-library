#!/usr/bin/env python3
"""Public search, recommendation, statistics, and constants routes."""

from database import get_statistics
from fastapi import APIRouter
from schemas import ConstantsResponse, SearchResponse, StatisticsResponse
from search_engine import CaseSearchEngine

router = APIRouter()
search_engine = CaseSearchEngine()


@router.get(
    "/api/search",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="Search cases by keyword",
)
async def search_cases_endpoint(q: str, status: str | None = "approved"):
    return {"success": True, "data": search_engine.search(q, status), "query": q}


@router.get(
    "/api/search/advanced",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="Filter cases by type, theme, status, and keyword",
)
async def advanced_search(
    type: str | None = None,
    theme: str | None = None,
    status: str = "approved",
    keyword: str | None = None,
    limit: int = 50,
):
    return {
        "success": True,
        "data": search_engine.advanced_filter(
            type_filter=type,
            theme_filter=theme,
            status_filter=status,
            keyword_filter=keyword,
            limit=limit,
        ),
    }


@router.get(
    "/api/recommendations/{case_id}",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="Get related case recommendations",
)
async def get_recommendations_endpoint(case_id: int, limit: int = 5):
    return {"success": True, "data": search_engine.get_recommendations(case_id, limit)}


@router.get(
    "/api/trending",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="List trending public cases",
)
async def get_trending_cases(limit: int = 10):
    return {"success": True, "data": search_engine.get_trending(limit)}


@router.get(
    "/api/latest",
    response_model=SearchResponse,
    response_model_exclude_none=True,
    summary="List latest public cases",
)
async def get_latest_cases(limit: int = 10):
    return {"success": True, "data": search_engine.get_latest(limit)}


@router.get(
    "/api/statistics",
    response_model=StatisticsResponse,
    summary="Get public case statistics",
    description="Return aggregate counts for approved, visible cases.",
)
async def get_statistics_endpoint():
    return {"success": True, "data": get_statistics()}


@router.get(
    "/api/constants",
    response_model=ConstantsResponse,
    summary="Get runtime labels and constants",
    description="Return case type, theme, and status labels used by the frontend.",
)
async def get_constants():
    return {
        "success": True,
        "data": {
            "case_types": {
                "TYPE_A": "思政课教学案例",
                "TYPE_B": "课程思政共享资源案例",
                "TYPE_C": "实践育人案例",
            },
            "themes": ["强国建设", "实践育人", "数字赋能", "铸魂育人"],
            "statuses": {
                "draft": "草稿",
                "pending_review": "待审核",
                "approved": "已通过",
                "needs_revision": "退回修改",
            },
        },
    }
