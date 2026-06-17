"""Business orchestration for case workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.security import get_case_owner_username
from backend.app.domains.cases.processing import process_new_case
from backend.app.domains.cases.serializers import serialize_public_case
from backend.repositories.cases import (
    count_cases,
    create_case,
    decrement_like_count,
    delete_case,
    get_all_cases,
    get_all_public_cases,
    get_case,
    increment_like_count,
    increment_view_count,
    set_case_hidden,
    update_case,
)
from backend.repositories.reviews import submit_for_review
from backend.services.abuse import (
    PublicInteractionIdentity,
    PublicInteractionRateLimitExceededError,
    ensure_public_interaction_allowed,
)

AUTHOR_LOCKED_REVIEW_STATUSES = {"pending_review", "approved"}


class CaseServiceError(Exception):
    """Domain error that routes map to HTTP responses."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class CaseListResult:
    data: list[dict]
    total: int


def _require_user(current_user: dict | None) -> dict:
    if not current_user:
        raise CaseServiceError(401, "请先登录")
    return current_user


def _is_admin(current_user: dict | None) -> bool:
    return bool(current_user and current_user.get("role") == "admin")


def _is_owner(current_user: dict | None, owner_username: str) -> bool:
    return bool(current_user and current_user.get("username") == owner_username)


def list_cases_for_user(
    *,
    status: str | None = "approved",
    offset: int = 0,
    limit: int = 50,
    author: str | None = None,
    current_user: dict | None = None,
) -> CaseListResult:
    if status == "draft" and not author:
        user = _require_user(current_user)
        author = user.get("username")

    is_admin = _is_admin(current_user)
    is_public_library = (status == "approved") and not author
    if not author and not is_public_library:
        if not current_user:
            raise CaseServiceError(401, "请先登录")
        if not is_admin:
            raise CaseServiceError(403, "仅管理员可以查看全站审核队列")

    if author:
        user = _require_user(current_user)
        if user.get("role") != "admin" and user.get("username") != author:
            raise CaseServiceError(403, "无权查看该用户案例")
        if status == "draft" and user.get("username") != author:
            raise CaseServiceError(403, "无权查看该用户草稿")

    is_self_view = bool(author and current_user and current_user.get("username") == author)
    include_hidden = (is_admin or is_self_view) and not is_public_library
    if is_public_library:
        return CaseListResult(
            data=get_all_public_cases(status, offset, limit),
            total=count_cases(status, author, include_hidden=False),
        )

    return CaseListResult(
        data=get_all_cases(status, offset, limit, author, include_hidden=include_hidden),
        total=count_cases(status, author, include_hidden=include_hidden),
    )


def get_case_detail_for_user(
    case_id: int,
    *,
    increment_view: bool = True,
    current_user: dict | None = None,
) -> dict:
    case = get_case(case_id)
    if not case:
        raise CaseServiceError(404, "案例不存在")

    owner_username = get_case_owner_username(case)
    is_admin = _is_admin(current_user)
    is_owner = _is_owner(current_user, owner_username)

    if case.get("status") == "draft" and not is_owner:
        raise CaseServiceError(403, "无权查看该草稿")

    if case.get("is_hidden") and not (is_admin or is_owner):
        raise CaseServiceError(404, "案例不存在")
    is_public_reader = not (is_admin or is_owner)
    if is_public_reader and case.get("status") != "approved":
        raise CaseServiceError(403, "无权查看该案例")

    if (
        increment_view
        and case.get("status") == "approved"
        and not case.get("is_hidden")
        and not increment_view_count(case_id)
    ):
        raise CaseServiceError(404, "案例不存在")

    if is_public_reader:
        public_case = serialize_public_case(case)
        if public_case is None:
            raise CaseServiceError(404, "案例不存在")
        return public_case
    return case


def create_case_for_user(
    *,
    title: str,
    content: str,
    source_material: str = "",
    department: str = "",
    type: str = "TYPE_A",
    theme: str = "铸魂育人",
    target_stages: str | None = None,
    status: str = "pending_review",
    ai_reviews: str | None = None,
    auto_process: bool = False,
    current_user: dict | None = None,
) -> dict:
    user = _require_user(current_user)

    if status not in ("draft", "pending_review"):
        raise CaseServiceError(400, "非法的初始状态")

    owner_username = user.get("username", "")
    author = user.get("nickname") or owner_username

    case_type = type or "TYPE_A"
    case_theme = theme or "铸魂育人"

    if auto_process:
        case_ids = process_new_case(
            content,
            title,
            author,
            department,
            case_type,
            case_theme,
            owner_username,
        )
        return {"case_ids": case_ids}

    case_id = create_case(
        {
            "title": title,
            "type": case_type,
            "theme": case_theme,
            "target_stages": target_stages,
            "content": content,
            "source_material": source_material,
            "author": author,
            "owner_username": owner_username,
            "department": department,
            "status": status,
            "ai_reviews": ai_reviews,
        }
    )
    return {"case_id": case_id}


def update_case_for_user(
    case_id: int,
    *,
    title: str | None = None,
    content: str | None = None,
    source_material: str | None = None,
    author: str | None = None,
    department: str | None = None,
    type: str | None = None,
    theme: str | None = None,
    target_stages: str | None = None,
    ai_reviews: str | None = None,
    change_reason: str = "",
    current_user: dict | None = None,
) -> None:
    user = _require_user(current_user)

    existing_case = get_case(case_id)
    if not existing_case:
        raise CaseServiceError(404, "案例不存在")
    owner_username = get_case_owner_username(existing_case)
    if user.get("role") != "admin" and user.get("username") != owner_username:
        raise CaseServiceError(403, "无权修改该案例")
    if existing_case.get("status") == "draft" and user.get("username") != owner_username:
        raise CaseServiceError(403, "无权修改该草稿")

    case_data: dict[str, Any] = {}
    for field, value in {
        "title": title,
        "content": content,
        "author": author,
        "department": department,
        "type": type,
        "theme": theme,
        "target_stages": target_stages,
        "ai_reviews": ai_reviews,
    }.items():
        if value is not None and value != "":
            case_data[field] = value
    if source_material is not None:
        case_data["source_material"] = source_material

    if (
        case_data
        and user.get("role") != "admin"
        and existing_case.get("status") in AUTHOR_LOCKED_REVIEW_STATUSES
    ):
        raise CaseServiceError(
            403,
            "案例已提交审核或已通过，需退回修改后才能更新审核内容",
        )

    updated_by = user.get("username", "")
    if not update_case(case_id, case_data, updated_by, change_reason):
        if get_case(case_id):
            raise CaseServiceError(400, "案例没有实际变更")
        raise CaseServiceError(404, "案例不存在")


def delete_case_for_user(case_id: int, *, current_user: dict | None = None) -> dict:
    user = _require_user(current_user)

    case = get_case(case_id)
    if not case:
        raise CaseServiceError(404, "案例不存在")
    owner_username = get_case_owner_username(case)
    if user.get("role") != "admin" and user.get("username") != owner_username:
        raise CaseServiceError(403, "无权删除该案例")
    if case.get("status") == "draft" and user.get("username") != owner_username:
        raise CaseServiceError(403, "无权删除该草稿")

    result = delete_case(case_id, deleted_by=user.get("username", ""))
    if not result.get("success"):
        raise CaseServiceError(404, "案例不存在")
    return result


def submit_case_for_user(
    case_id: int,
    *,
    version_id: int | None = None,
    current_user: dict | None = None,
) -> None:
    user = _require_user(current_user)

    case = get_case(case_id, include_deleted=True)
    if not case:
        raise CaseServiceError(404, "案例不存在")

    owner_username = get_case_owner_username(case)
    if user.get("role") != "admin" and user.get("username") != owner_username:
        raise CaseServiceError(403, "无权提交该案例")

    if not submit_for_review(case_id, version_id=version_id):
        raise CaseServiceError(400, "案例状态不允许提交审核")


def submit_case_version(
    case_id: int,
    *,
    version_id: int | None = None,
    current_user: dict | None = None,
) -> None:
    return submit_case_for_user(
        case_id,
        version_id=version_id,
        current_user=current_user,
    )


def like_case(case_id: int, identity: PublicInteractionIdentity | None = None) -> None:
    try:
        ensure_public_interaction_allowed("case.like", identity)
    except PublicInteractionRateLimitExceededError as exc:
        raise CaseServiceError(429, "操作过于频繁，请稍后再试") from exc
    if not increment_like_count(case_id):
        raise CaseServiceError(404, "案例不存在")


def unlike_case(case_id: int, identity: PublicInteractionIdentity | None = None) -> None:
    try:
        ensure_public_interaction_allowed("case.unlike", identity)
    except PublicInteractionRateLimitExceededError as exc:
        raise CaseServiceError(429, "操作过于频繁，请稍后再试") from exc
    if not decrement_like_count(case_id):
        case = get_case(case_id)
        if case and case.get("status") == "approved" and not case.get("is_hidden"):
            raise CaseServiceError(400, "点赞数已经为0")
        raise CaseServiceError(404, "案例不存在")


def set_case_visibility_for_admin(
    case_id: int,
    *,
    hidden: bool,
    current_user: dict | None = None,
) -> bool:
    if not current_user or current_user.get("role") != "admin":
        raise CaseServiceError(403, "仅管理员可以隐藏或展示案例")

    if not get_case(case_id):
        raise CaseServiceError(404, "案例不存在")

    if not set_case_hidden(case_id, hidden):
        raise CaseServiceError(400, "操作失败")
    return bool(hidden)


__all__ = [
    "AUTHOR_LOCKED_REVIEW_STATUSES",
    "CaseListResult",
    "CaseServiceError",
    "create_case_for_user",
    "delete_case_for_user",
    "get_case_detail_for_user",
    "like_case",
    "list_cases_for_user",
    "set_case_visibility_for_admin",
    "submit_case_for_user",
    "submit_case_version",
    "unlike_case",
    "update_case_for_user",
]
