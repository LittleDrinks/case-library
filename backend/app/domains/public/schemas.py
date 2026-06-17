"""Public search, statistics, and constants API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.domains.cases.schemas import CaseData


class SearchResponse(BaseModel):
    success: bool = True
    data: list[CaseData]
    query: str | None = None


class StatisticsData(BaseModel):
    total_cases: int | None = None
    total_views: int | None = None
    total_likes: int | None = None
    by_type: dict[str, int] = Field(default_factory=dict)
    by_theme: dict[str, int] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class StatisticsResponse(BaseModel):
    success: bool = True
    data: StatisticsData


class ConstantsData(BaseModel):
    case_types: dict[str, str]
    themes: list[str]
    statuses: dict[str, str]


class ConstantsResponse(BaseModel):
    success: bool = True
    data: ConstantsData


__all__ = [
    "ConstantsData",
    "ConstantsResponse",
    "SearchResponse",
    "StatisticsData",
    "StatisticsResponse",
]
