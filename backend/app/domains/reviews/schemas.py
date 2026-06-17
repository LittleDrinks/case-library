"""Human review API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]


class ReviewData(BaseModel):
    id: int | None = None
    case_id: int | None = None
    version_id: int | None = None
    reviewer: str | None = None
    comment: str | None = None
    paragraph_comments: list[JsonDict] = Field(default_factory=list)
    status: str | None = None
    created_at: str | None = None
    review_at: str | None = None

    model_config = {"extra": "allow"}


class ReviewListResponse(BaseModel):
    success: bool = True
    data: list[ReviewData]


__all__ = ["JsonDict", "ReviewData", "ReviewListResponse"]
