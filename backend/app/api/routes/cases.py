#!/usr/bin/env python3
"""Case CRUD and lifecycle routes."""

from fastapi import APIRouter, Form, HTTPException, Request

from backend.app.core.dependencies import BearerCredentials, OptionalBearer, RequiredBearer
from backend.app.core.security import get_current_user
from backend.app.domains.cases.schemas import (
    CaseCreateResponse,
    CaseDeleteResponse,
    CaseDetailResponse,
    CaseListResponse,
    CaseVisibilityResponse,
    SuccessMessageResponse,
)
from backend.app.domains.cases.service import (
    CaseServiceError,
    create_case_for_user,
    delete_case_for_user,
    get_case_detail_for_user,
    list_cases_for_user,
    set_case_visibility_for_admin,
    submit_case_for_user,
    update_case_for_user,
)
from backend.app.domains.cases.service import (
    like_case as like_case_service,
)
from backend.app.domains.cases.service import (
    unlike_case as unlike_case_service,
)
from backend.services.abuse import public_interaction_identity

router = APIRouter()


def _raise_case_error(exc: CaseServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/api/cases",
    response_model=CaseListResponse,
    response_model_exclude_none=True,
    summary="List cases",
    description=(
        "List public approved cases by default. Draft, author-scoped, and admin views "
        "require a bearer token and are filtered by the current user's role."
    ),
)
async def list_cases(
    request: Request,
    status: str | None = "approved",
    offset: int = 0,
    limit: int = 50,
    author: str | None = None,
    _credentials: BearerCredentials = OptionalBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        result = list_cases_for_user(
            status=status,
            offset=offset,
            limit=limit,
            author=author,
            current_user=current_user,
        )
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "data": result.data, "total": result.total}


@router.get(
    "/api/cases/{case_id}",
    response_model=CaseDetailResponse,
    response_model_exclude_none=True,
    summary="Get case detail",
    description=(
        "Return one case. Public approved cases are readable without auth; draft or "
        "hidden cases are visible only to the owner or an admin."
    ),
)
async def get_case_detail(
    case_id: int,
    request: Request,
    increment_view: bool = True,
    _credentials: BearerCredentials = OptionalBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        data = get_case_detail_for_user(
            case_id,
            increment_view=increment_view,
            current_user=current_user,
        )
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "data": data}


@router.post(
    "/api/cases",
    response_model=CaseCreateResponse,
    summary="Create a case",
    description=(
        "Create a draft or pending-review case from form fields. Requires a bearer "
        "token. `auto_process=true` may create multiple processed case records."
    ),
)
async def create_new_case(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    source_material: str = Form(""),
    department: str = Form(""),
    type: str = Form("TYPE_A"),
    theme: str = Form("铸魂育人"),
    status: str = Form("pending_review"),
    ai_reviews: str | None = Form(None),
    auto_process: bool = Form(False),
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        result = create_case_for_user(
            title=title,
            content=content,
            source_material=source_material,
            department=department,
            type=type,
            theme=theme,
            status=status,
            ai_reviews=ai_reviews,
            auto_process=auto_process,
            current_user=current_user,
        )
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "message": "案例创建成功", **result}


async def _update_existing_case_impl(
    case_id: int,
    title: str | None,
    content: str | None,
    source_material: str | None,
    author: str | None,
    department: str | None,
    type: str | None,
    theme: str | None,
    ai_reviews: str | None,
    change_reason: str,
    current_user: dict | None,
):
    try:
        update_case_for_user(
            case_id,
            title=title,
            content=content,
            source_material=source_material,
            author=author,
            department=department,
            type=type,
            theme=theme,
            ai_reviews=ai_reviews,
            change_reason=change_reason,
            current_user=current_user,
        )
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "message": "案例更新成功"}


@router.put(
    "/api/cases/{case_id}",
    response_model=SuccessMessageResponse,
    summary="Update a case",
    description=(
        "Update editable case fields and record a version entry. Owners can edit "
        "draft or revision-required cases; pending-review or approved content must "
        "be returned for revision first. Admin bearer auth can update review states."
    ),
)
async def update_existing_case(
    case_id: int,
    request: Request,
    title: str | None = Form(None),
    content: str | None = Form(None),
    source_material: str | None = Form(None),
    author: str | None = Form(None),
    department: str | None = Form(None),
    type: str | None = Form(None),
    theme: str | None = Form(None),
    ai_reviews: str | None = Form(None),
    change_reason: str = Form(""),
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    return await _update_existing_case_impl(
        case_id,
        title,
        content,
        source_material,
        author,
        department,
        type,
        theme,
        ai_reviews,
        change_reason,
        current_user,
    )


@router.post(
    "/api/cases/{case_id}",
    response_model=SuccessMessageResponse,
    summary="Update a case with POST compatibility",
    description=(
        "Compatibility endpoint with the same behavior as PUT /api/cases/{case_id}; "
        "owner edits are locked while a case is pending review or approved."
    ),
)
async def update_existing_case_post_compat(
    case_id: int,
    request: Request,
    title: str | None = Form(None),
    content: str | None = Form(None),
    source_material: str | None = Form(None),
    author: str | None = Form(None),
    department: str | None = Form(None),
    type: str | None = Form(None),
    theme: str | None = Form(None),
    ai_reviews: str | None = Form(None),
    change_reason: str = Form(""),
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    return await _update_existing_case_impl(
        case_id,
        title,
        content,
        source_material,
        author,
        department,
        type,
        theme,
        ai_reviews,
        change_reason,
        current_user,
    )


@router.delete(
    "/api/cases/{case_id}",
    response_model=CaseDeleteResponse,
    summary="Delete a case",
    description=(
        "Soft-delete a case and return statistics about the removed library item. "
        "Requires owner or admin bearer auth."
    ),
)
async def delete_case_endpoint(
    case_id: int,
    request: Request,
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        result = delete_case_for_user(case_id, current_user=current_user)
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {
        "success": True,
        "message": "案例删除成功",
        "deleted_stats": {
            "was_in_library": result.get("was_in_library", False),
            "view_count": result.get("view_count", 0),
            "like_count": result.get("like_count", 0),
            "type": result.get("type"),
            "theme": result.get("theme"),
        },
    }


@router.post(
    "/api/cases/{case_id}/submit",
    response_model=SuccessMessageResponse,
    summary="Submit a case for human review",
    description="Move a draft or revision-required case to pending review. Requires owner auth.",
)
async def submit_case_for_review(
    case_id: int,
    request: Request,
    version_id: int | None = Form(None),
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        submit_case_for_user(case_id, version_id=version_id, current_user=current_user)
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "message": "案例已提交审核"}


@router.post(
    "/api/cases/{case_id}/like",
    response_model=SuccessMessageResponse,
    summary="Like a public case",
)
async def like_case(case_id: int, request: Request):
    try:
        like_case_service(case_id, identity=public_interaction_identity(request))
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "message": "点赞成功"}


@router.post(
    "/api/cases/{case_id}/unlike",
    response_model=SuccessMessageResponse,
    summary="Remove one like from a case",
)
async def unlike_case(case_id: int, request: Request):
    try:
        unlike_case_service(case_id, identity=public_interaction_identity(request))
    except CaseServiceError as exc:
        _raise_case_error(exc)
    return {"success": True, "message": "取消点赞成功"}


@router.post(
    "/api/cases/{case_id}/visibility",
    response_model=CaseVisibilityResponse,
    summary="Hide or show a case",
    description="Admin-only visibility toggle. Requires a bearer token for an admin user.",
)
async def toggle_case_visibility(
    case_id: int,
    request: Request,
    hidden: bool = Form(...),
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        is_hidden = set_case_visibility_for_admin(
            case_id,
            hidden=hidden,
            current_user=current_user,
        )
    except CaseServiceError as exc:
        _raise_case_error(exc)

    return {
        "success": True,
        "message": "案例已隐藏" if is_hidden else "案例已展示",
        "is_hidden": is_hidden,
    }
