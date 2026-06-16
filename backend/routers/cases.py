#!/usr/bin/env python3
"""Case CRUD and lifecycle routes."""

from case_processor import process_new_case
from database import (
    count_cases,
    create_case,
    decrement_like_count,
    delete_case,
    get_all_cases,
    get_all_public_cases,
    get_case,
    increment_like_count,
    increment_view_count,
    serialize_public_case,
    set_case_hidden,
    submit_for_review,
    update_case,
)
from dependencies import BearerCredentials, OptionalBearer, RequiredBearer
from fastapi import APIRouter, Form, HTTPException, Request
from schemas import (
    CaseCreateResponse,
    CaseDeleteResponse,
    CaseDetailResponse,
    CaseListResponse,
    CaseVisibilityResponse,
    SuccessMessageResponse,
)
from security import get_case_owner_username, get_current_user

router = APIRouter()
AUTHOR_LOCKED_REVIEW_STATUSES = {"pending_review", "approved"}


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
    status: str | None = "approved",
    offset: int = 0,
    limit: int = 50,
    author: str | None = None,
    request: Request = None,
    _credentials: BearerCredentials = OptionalBearer,
):
    current_user = get_current_user(dict(request.headers)) if request else None
    if status == "draft" and not author:
        if not current_user:
            raise HTTPException(status_code=401, detail="请先登录")
        author = current_user.get("username")

    is_admin = bool(current_user and current_user.get("role") == "admin")
    is_public_library = (status == "approved") and not author
    if not author and not is_public_library:
        if not current_user:
            raise HTTPException(status_code=401, detail="请先登录")
        if not is_admin:
            raise HTTPException(status_code=403, detail="仅管理员可以查看全站审核队列")

    if author:
        if not current_user:
            raise HTTPException(status_code=401, detail="请先登录")
        if current_user.get("role") != "admin" and current_user.get("username") != author:
            raise HTTPException(status_code=403, detail="无权查看该用户案例")
        if status == "draft" and current_user.get("username") != author:
            raise HTTPException(status_code=403, detail="无权查看该用户草稿")

    is_self_view = bool(author and current_user and current_user.get("username") == author)
    include_hidden = (is_admin or is_self_view) and not is_public_library
    if is_public_library:
        return {
            "success": True,
            "data": get_all_public_cases(status, offset, limit),
            "total": count_cases(status, author, include_hidden=False),
        }

    return {
        "success": True,
        "data": get_all_cases(status, offset, limit, author, include_hidden=include_hidden),
        "total": count_cases(status, author, include_hidden=include_hidden),
    }


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
    increment_view: bool = True,
    request: Request = None,
    _credentials: BearerCredentials = OptionalBearer,
):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    current_user = get_current_user(dict(request.headers)) if request else None
    owner_username = get_case_owner_username(case)
    is_admin = bool(current_user and current_user.get("role") == "admin")
    is_owner = bool(current_user and current_user.get("username") == owner_username)

    if case.get("status") == "draft" and not is_owner:
        raise HTTPException(status_code=403, detail="无权查看该草稿")

    if case.get("is_hidden") and not (is_admin or is_owner):
        raise HTTPException(status_code=404, detail="案例不存在")
    is_public_reader = not (is_admin or is_owner)
    if is_public_reader and case.get("status") != "approved":
        raise HTTPException(status_code=403, detail="无权查看该案例")

    if (
        increment_view
        and case.get("status") == "approved"
        and not case.get("is_hidden")
        and not increment_view_count(case_id)
    ):
        raise HTTPException(status_code=404, detail="案例不存在")

    return {"success": True, "data": serialize_public_case(case) if is_public_reader else case}


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
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    if status not in ("draft", "pending_review"):
        raise HTTPException(status_code=400, detail="非法的初始状态")

    owner_username = current_user.get("username", "")
    author = current_user.get("nickname") or owner_username

    case_type = type or "TYPE_A"
    case_theme = theme or "铸魂育人"

    if auto_process:
        case_ids = process_new_case(
            content, title, author, department, case_type, case_theme, owner_username
        )
        return {"success": True, "message": "案例创建成功", "case_ids": case_ids}

    case_id = create_case(
        {
            "title": title,
            "type": case_type,
            "theme": case_theme,
            "content": content,
            "source_material": source_material,
            "author": author,
            "owner_username": owner_username,
            "department": department,
            "status": status,
            "ai_reviews": ai_reviews,
        }
    )
    return {"success": True, "message": "案例创建成功", "case_id": case_id}


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
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    existing_case = get_case(case_id)
    if not existing_case:
        raise HTTPException(status_code=404, detail="案例不存在")
    owner_username = get_case_owner_username(existing_case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权修改该案例")
    if existing_case.get("status") == "draft" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权修改该草稿")

    case_data = {}
    for field, value in {
        "title": title,
        "content": content,
        "author": author,
        "department": department,
        "type": type,
        "theme": theme,
        "ai_reviews": ai_reviews,
    }.items():
        if value is not None and value != "":
            case_data[field] = value
    if source_material is not None:
        case_data["source_material"] = source_material

    if (
        case_data
        and current_user.get("role") != "admin"
        and existing_case.get("status") in AUTHOR_LOCKED_REVIEW_STATUSES
    ):
        raise HTTPException(
            status_code=403,
            detail="案例已提交审核或已通过，需退回修改后才能更新审核内容",
        )

    updated_by = current_user.get("username", "")
    if not update_case(case_id, case_data, updated_by, change_reason):
        if get_case(case_id):
            raise HTTPException(status_code=400, detail="案例没有实际变更")
        raise HTTPException(status_code=404, detail="案例不存在")

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
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    owner_username = get_case_owner_username(case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权删除该案例")
    if case.get("status") == "draft" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权删除该草稿")

    result = delete_case(case_id, deleted_by=current_user.get("username", ""))
    if not result.get("success"):
        raise HTTPException(status_code=404, detail="案例不存在")

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
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    case = get_case(case_id, include_deleted=True)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")

    owner_username = get_case_owner_username(case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权提交该案例")

    if not submit_for_review(case_id, version_id=version_id):
        raise HTTPException(status_code=400, detail="案例状态不允许提交审核")
    return {"success": True, "message": "案例已提交审核"}


@router.post(
    "/api/cases/{case_id}/like",
    response_model=SuccessMessageResponse,
    summary="Like a public case",
)
async def like_case(case_id: int):
    if not increment_like_count(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True, "message": "点赞成功"}


@router.post(
    "/api/cases/{case_id}/unlike",
    response_model=SuccessMessageResponse,
    summary="Remove one like from a case",
)
async def unlike_case(case_id: int):
    if not decrement_like_count(case_id):
        case = get_case(case_id)
        if case and case.get("status") == "approved" and not case.get("is_hidden"):
            raise HTTPException(status_code=400, detail="点赞数已经为0")
        raise HTTPException(status_code=404, detail="案例不存在")
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
    if not current_user or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可以隐藏或展示案例")

    if not get_case(case_id):
        raise HTTPException(status_code=404, detail="案例不存在")

    if not set_case_hidden(case_id, hidden):
        raise HTTPException(status_code=400, detail="操作失败")

    return {
        "success": True,
        "message": "案例已隐藏" if hidden else "案例已展示",
        "is_hidden": bool(hidden),
    }
