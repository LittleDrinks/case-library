"""Case and version API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]


class SuccessMessageResponse(BaseModel):
    success: bool = True
    message: str


class CaseData(BaseModel):
    id: int | None = None
    title: str | None = None
    type: str | None = None
    theme: str | None = None
    content: str | None = None
    source_material: str | None = None
    author: str | None = None
    owner_username: str | None = None
    department: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    submitted_at: str | None = None
    review_at: str | None = None
    display_at: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    is_hidden: bool | None = None
    keywords: list[str] | None = None
    ai_reviews: list[JsonDict] | None = None

    model_config = {"extra": "allow"}


class CaseListResponse(BaseModel):
    success: bool = True
    data: list[CaseData]
    total: int


class CaseDetailResponse(BaseModel):
    success: bool = True
    data: CaseData


class CaseCreateResponse(BaseModel):
    success: bool = True
    message: str
    case_id: int | None = None
    case_ids: list[int] | None = None


class CaseDeletedStats(BaseModel):
    was_in_library: bool
    view_count: int
    like_count: int
    type: str | None = None
    theme: str | None = None


class CaseDeleteResponse(BaseModel):
    success: bool = True
    message: str
    deleted_stats: CaseDeletedStats


class CaseVisibilityResponse(BaseModel):
    success: bool = True
    message: str
    is_hidden: bool


class VersionData(BaseModel):
    id: int | None = None
    case_id: int | None = None
    version_number: int | None = None
    title: str | None = None
    type: str | None = None
    theme: str | None = None
    content: str | None = None
    source_material: str | None = None
    author: str | None = None
    owner_username: str | None = None
    created_by: str | None = None
    paragraphs: list[JsonDict] = Field(default_factory=list)
    ai_review: JsonDict | None = None
    admin_comments: list[JsonDict] = Field(default_factory=list)
    change_reason: str | None = None
    created_at: str | None = None

    model_config = {"extra": "allow"}


class VersionListResponse(BaseModel):
    success: bool = True
    data: list[VersionData]


__all__ = [
    "CaseCreateResponse",
    "CaseData",
    "CaseDeleteResponse",
    "CaseDeletedStats",
    "CaseDetailResponse",
    "CaseListResponse",
    "CaseVisibilityResponse",
    "JsonDict",
    "SuccessMessageResponse",
    "VersionData",
    "VersionListResponse",
]
