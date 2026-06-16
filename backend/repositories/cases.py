"""Case repository helpers."""

from __future__ import annotations

from typing import Any

from db.connection import get_db
from db.constants import VERSIONED_FIELDS
from db.counters import _insert_with_generated_id
from db.datetime import _normalize_datetime_fields
from db.validators import (
    _bounded_limit,
    _normalize_ai_reviews,
    _normalize_keywords,
    _now,
    _validate_case_status,
)
from pymongo import DESCENDING
from serializers import serialize_case, serialize_public_case
from services.public import invalidate_statistics_cache
from services.reviews import split_paragraphs


def create_case(case_data: dict) -> int:
    status = case_data.get("status", "draft")
    _validate_case_status(status)

    now = _now()
    doc = {
        "title": case_data.get("title", ""),
        "type": case_data.get("type", ""),
        "theme": case_data.get("theme", ""),
        "content": case_data.get("content", ""),
        "source_material": case_data.get("source_material", ""),
        "status": status,
        "submitted_at": case_data.get("submitted_at") or (now if status == "pending_review" else None),
        "author": case_data.get("author", ""),
        "owner_username": case_data.get("owner_username", ""),
        "department": case_data.get("department", ""),
        "keywords": _normalize_keywords(case_data.get("keywords", [])),
        "created_at": case_data.get("created_at") or now,
        "updated_at": case_data.get("updated_at") or now,
        "is_approved": bool(case_data.get("is_approved", False)),
        "is_in_library": bool(case_data.get("is_in_library", False)),
        "is_hidden": bool(case_data.get("is_hidden", False)),
        "view_count": int(case_data.get("view_count") or 0),
        "like_count": int(case_data.get("like_count") or 0),
        "ai_reviews": _normalize_ai_reviews(case_data.get("ai_reviews")),
    }

    if case_data.get("deployed_at") is not None:
        doc["deployed_at"] = case_data.get("deployed_at")
    if case_data.get("deployed_by") is not None:
        doc["deployed_by"] = case_data.get("deployed_by")

    case_id = _insert_with_generated_id("cases", doc)

    version_doc = {
        "case_id": case_id,
        "version_number": 1,
        "title": doc.get("title", ""),
        "type": doc.get("type", ""),
        "theme": doc.get("theme", ""),
        "content": doc.get("content", ""),
        "source_material": doc.get("source_material", ""),
        "author": doc.get("author", ""),
        "department": doc.get("department", ""),
        "keywords": _normalize_keywords(doc.get("keywords")),
        "owner_username": doc.get("owner_username", ""),
        "created_by": doc.get("owner_username") or doc.get("author", ""),
        "paragraphs": split_paragraphs(doc.get("content", "")),
        "ai_review": None,
        "admin_comments": [],
        "changed_by": doc.get("author", ""),
        "change_reason": "初始创建",
        "created_at": now,
    }
    version_id = _insert_with_generated_id("versions", version_doc)
    if status == "pending_review":
        get_db().cases.update_one(
            {"id": case_id},
            {
                "$set": _normalize_datetime_fields(
                    {"submitted_version_id": version_id, "submitted_at": doc["submitted_at"]}
                )
            },
        )
    if status == "approved" and not doc.get("is_hidden"):
        invalidate_statistics_cache()
    return case_id

def get_case(case_id: int, include_deleted: bool = False) -> dict | None:
    query: dict[str, Any] = {"id": int(case_id)}
    if not include_deleted:
        query["status"] = {"$ne": "deleted"}
    return serialize_case(get_db().cases.find_one(query))

def _author_aliases(author: str) -> list[str]:
    """Return the username plus any non-empty nickname so legacy cases that
    stored the nickname in the `author` field still match."""
    aliases = {author}
    user = get_db().users.find_one({"username": author}, projection={"nickname": 1})
    if user:
        nickname = user.get("nickname") or ""
        if nickname:
            aliases.add(nickname)
    return [a for a in aliases if a]

def _apply_hidden_filter(query: dict[str, Any], include_hidden: bool) -> dict[str, Any]:
    if include_hidden:
        return query
    query["is_hidden"] = {"$ne": True}
    return query

def _case_list_filter(
    status: str | None = None,
    author: str | None = None,
    include_deleted: bool = False,
    include_hidden: bool = True,
) -> dict[str, Any]:
    query: dict[str, Any] = {}

    if author:
        aliases = _author_aliases(author)
        query["$or"] = [
            {"owner_username": author},
            {"author": {"$in": aliases}},
        ]

    if status and status not in ("all", ""):
        if status == "rejected":
            query["status"] = "needs_revision"
        elif status in ("approved", "approved_all"):
            query["status"] = "approved"
        else:
            _validate_case_status(status)
            query["status"] = status
    elif status == "all" or not author:
        query["status"] = {"$nin": ["draft", "deleted"]}

    if not include_deleted:
        existing_status = query.get("status")
        if existing_status is None:
            query["status"] = {"$ne": "deleted"}
        elif isinstance(existing_status, dict):
            if "$nin" in existing_status:
                existing_status["$nin"] = list(set(existing_status["$nin"]) | {"deleted"})
            else:
                existing_status.setdefault("$ne", "deleted")
        elif existing_status == "deleted":
            query["status"] = {"$ne": "deleted"}

    _apply_hidden_filter(query, include_hidden)
    return query

def get_all_cases(
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
    author: str | None = None,
    include_hidden: bool = True,
) -> list[dict]:
    query = _case_list_filter(status=status, author=author, include_hidden=include_hidden)
    cursor = (
        get_db()
        .cases.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, int(offset)))
        .limit(_bounded_limit(limit))
    )
    return [serialize_case(row) for row in cursor]

def get_all_public_cases(
    status: str | None = "approved",
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    return [
        item
        for item in (
            serialize_public_case(row)
            for row in get_db()
            .cases.find(_case_list_filter(status=status, include_hidden=False))
            .sort("created_at", DESCENDING)
            .skip(max(0, int(offset)))
            .limit(_bounded_limit(limit))
        )
        if item is not None
    ]

def count_cases(
    status: str | None = None,
    author: str | None = None,
    include_hidden: bool = True,
) -> int:
    return get_db().cases.count_documents(
        _case_list_filter(status=status, author=author, include_hidden=include_hidden)
    )

def set_case_hidden(case_id: int, hidden: bool) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$set": _normalize_datetime_fields({"is_hidden": bool(hidden), "updated_at": _now()})},
    )
    if result.matched_count > 0 and result.modified_count > 0:
        invalidate_statistics_cache()
    return result.matched_count > 0

def _values_differ(field: str, current: dict, new_value: Any) -> bool:
    current_value = current.get(field)
    if field == "keywords":
        current_value = _normalize_keywords(current_value)
        new_value = _normalize_keywords(new_value)
    return current_value != new_value

def update_case(
    case_id: int, case_data: dict, updated_by: str = "system", change_reason: str = ""
) -> bool:
    db = get_db()
    current = db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
    if not current:
        return False

    if "status" in case_data:
        _validate_case_status(case_data.get("status"))

    allowed_fields = [
        "title",
        "type",
        "theme",
        "content",
        "source_material",
        "author",
        "department",
        "status",
        "is_approved",
        "is_in_library",
        "ai_reviews",
    ]
    updates = {field: case_data[field] for field in allowed_fields if field in case_data}

    if "keywords" in case_data:
        updates["keywords"] = _normalize_keywords(case_data.get("keywords"))
    if "ai_reviews" in case_data:
        updates["ai_reviews"] = _normalize_ai_reviews(case_data.get("ai_reviews"))

    changed_updates = {
        field: value for field, value in updates.items() if _values_differ(field, current, value)
    }
    if not changed_updates:
        return False

    version_changed = any(field in changed_updates for field in VERSIONED_FIELDS)
    changed_updates["updated_at"] = _now()

    result = db.cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$set": _normalize_datetime_fields(changed_updates)},
    )
    if result.matched_count == 0 or result.modified_count == 0:
        return False

    if version_changed:
        updated = db.cases.find_one({"id": int(case_id)})
        max_version = db.versions.find_one(
            {"case_id": int(case_id)},
            sort=[("version_number", DESCENDING)],
            projection={"version_number": 1},
        )
        new_version = int(max_version["version_number"]) + 1 if max_version else 1
        version_doc = {
            "case_id": int(case_id),
            "version_number": new_version,
            "title": (updated or {}).get("title", ""),
            "type": (updated or {}).get("type", ""),
            "theme": (updated or {}).get("theme", ""),
            "content": (updated or {}).get("content", ""),
            "source_material": (updated or {}).get("source_material", ""),
            "author": (updated or {}).get("author", ""),
            "department": (updated or {}).get("department", ""),
            "keywords": _normalize_keywords((updated or {}).get("keywords")),
            "owner_username": (updated or {}).get("owner_username", ""),
            "created_by": updated_by,
            "paragraphs": split_paragraphs((updated or {}).get("content", "")),
            "ai_review": None,
            "admin_comments": [],
            "changed_by": updated_by,
            "change_reason": change_reason,
            "created_at": _now(),
        }
        _insert_with_generated_id("versions", version_doc)

    if current.get("status") == "approved" or changed_updates.get("status") == "approved":
        invalidate_statistics_cache()
    return True

def delete_case(case_id: int, deleted_by: str = "") -> dict:
    db = get_db()
    case = db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
    if not case:
        return {
            "success": False,
            "was_in_library": False,
            "view_count": 0,
            "like_count": 0,
            "type": None,
            "theme": None,
        }

    now = _now()
    updates = {
        "status": "deleted",
        "updated_at": now,
        "deleted_at": now,
    }
    if deleted_by:
        updates["deleted_by"] = deleted_by

    result = db.cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$set": _normalize_datetime_fields(updates)},
    )
    # Intentionally keep reviews, versions and deployments for audit/history.
    if result.matched_count > 0 and case.get("status") == "approved" and not case.get("is_hidden"):
        invalidate_statistics_cache()

    return {
        "success": result.matched_count > 0,
        "was_in_library": bool(case.get("is_in_library", False)),
        "view_count": int(case.get("view_count") or 0),
        "like_count": int(case.get("like_count") or 0),
        "type": case.get("type"),
        "theme": case.get("theme"),
    }

def backfill_owner_username() -> dict[str, int]:
    """Repair legacy cases that are missing `owner_username`.

    For each case where `owner_username` is missing/empty, look up a user whose
    `nickname` or `username` matches the case's `author` field and copy that
    user's `username` into `owner_username`. Without this, "我的提交" cannot
    locate cases the user authored before `owner_username` was tracked.
    """
    db = get_db()
    nickname_to_username: dict[str, str] = {}
    username_set: set = set()
    for user in db.users.find({}, projection={"username": 1, "nickname": 1}):
        username = user.get("username") or ""
        nickname = user.get("nickname") or ""
        if username:
            username_set.add(username)
        if nickname and username and nickname not in nickname_to_username:
            nickname_to_username[nickname] = username

    missing_filter = {
        "$or": [
            {"owner_username": {"$exists": False}},
            {"owner_username": None},
            {"owner_username": ""},
        ]
    }

    fixed = 0
    skipped = 0
    for case in db.cases.find(missing_filter, projection={"id": 1, "author": 1}):
        author = (case.get("author") or "").strip()
        resolved = nickname_to_username.get(author) or (author if author in username_set else "")
        if not resolved:
            skipped += 1
            continue
        db.cases.update_one(
            {"id": case["id"]},
            {
                "$set": _normalize_datetime_fields(
                    {"owner_username": resolved, "updated_at": _now()}
                )
            },
        )
        fixed += 1
    return {"fixed": fixed, "skipped": skipped}

def increment_view_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": "approved", "is_hidden": {"$ne": True}},
        {"$inc": {"view_count": 1}},
    )
    changed = result.matched_count > 0 and result.modified_count > 0
    if changed:
        invalidate_statistics_cache()
    return changed

def increment_like_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": "approved", "is_hidden": {"$ne": True}},
        {"$inc": {"like_count": 1}},
    )
    changed = result.matched_count > 0 and result.modified_count > 0
    if changed:
        invalidate_statistics_cache()
    return changed

def decrement_like_count(case_id: int) -> bool:
    db = get_db()
    case_exists = (
        db.cases.count_documents(
            {"id": int(case_id), "status": "approved", "is_hidden": {"$ne": True}},
            limit=1,
        )
        > 0
    )
    if not case_exists:
        return False

    result = db.cases.update_one(
        {
            "id": int(case_id),
            "status": "approved",
            "is_hidden": {"$ne": True},
            "like_count": {"$gt": 0},
        },
        {"$inc": {"like_count": -1}},
    )
    if result.modified_count > 0:
        invalidate_statistics_cache()
        return True

    correction = db.cases.update_one(
        {
            "id": int(case_id),
            "status": "approved",
            "is_hidden": {"$ne": True},
            "like_count": {"$lt": 0},
        },
        {"$set": {"like_count": 0}},
    )
    changed = correction.modified_count > 0
    if changed:
        invalidate_statistics_cache()
    return changed
