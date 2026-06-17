#!/usr/bin/env python3
"""Human review and history routes."""

from fastapi import APIRouter, Form, HTTPException, Request

from backend.app.core.dependencies import (
    BearerCredentials,
    OptionalBearer,
    RequiredBearer,
    ensure_case_history_visible,
)
from backend.app.core.security import get_current_user
from backend.app.domains.cases.schemas import SuccessMessageResponse, VersionListResponse
from backend.app.domains.reviews.schemas import ReviewListResponse
from backend.repositories.reviews import get_reviews, review_case
from backend.repositories.versions import get_case_versions

router = APIRouter()


@router.post(
    "/api/reviews/{case_id}",
    response_model=SuccessMessageResponse,
    summary="Review a submitted case",
    description=(
        "Admin-only human review action. Form status accepts approve/approved or "
        "reject/rejected/needs_revision; reject means returned for revision."
    ),
)
async def review_case_endpoint(
    case_id: int,
    request: Request,
    comment: str = Form(...),
    status: str = Form(...),
    version_id: int | None = Form(None),
    paragraph_comments: str | None = Form(None),
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可以审核案例")
    reviewer = current_user.get("username", "")
    try:
        reviewed = review_case(
            case_id,
            reviewer,
            comment,
            status,
            version_id=version_id,
            paragraph_comments=paragraph_comments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not reviewed:
        raise HTTPException(status_code=400, detail="审核失败")
    return {"success": True, "message": "审核完成"}


@router.get(
    "/api/reviews/{case_id}",
    response_model=ReviewListResponse,
    summary="List case review records",
    description="Return human review history. Visible only to admins or the case owner.",
)
async def get_case_reviews(
    case_id: int,
    request: Request,
    _credentials: BearerCredentials = OptionalBearer,
):
    current_user = get_current_user(dict(request.headers))
    ensure_case_history_visible(case_id, current_user)
    return {"success": True, "data": get_reviews(case_id)}


@router.get(
    "/api/versions/{case_id}",
    response_model=VersionListResponse,
    summary="List case version history",
    description="Return edit history. Visible only to admins or the case owner.",
)
async def get_case_version_history(
    case_id: int,
    request: Request,
    _credentials: BearerCredentials = OptionalBearer,
):
    current_user = get_current_user(dict(request.headers))
    ensure_case_history_visible(case_id, current_user)
    return {"success": True, "data": get_case_versions(case_id)}
