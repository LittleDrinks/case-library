"""Mongo document serializers for API compatibility payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from db.connection import get_db
from db.constants import DATETIME_FIELDS, PUBLIC_REVIEW_SNAPSHOT_FIELDS
from db.datetime import format_beijing_datetime
from db.validators import _normalize_ai_reviews, _normalize_keywords
from services.reviews import split_paragraphs


def serialize_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_beijing_datetime(value)
    return value

def serialize_doc(doc: dict | None) -> dict | None:
    if doc is None:
        return None

    serialized: dict[str, Any] = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
        elif key in DATETIME_FIELDS:
            serialized[key] = format_beijing_datetime(value)
        elif isinstance(value, datetime):
            serialized[key] = serialize_datetime(value)
        elif isinstance(value, list):
            serialized[key] = [
                serialize_doc(item) if isinstance(item, dict) else serialize_datetime(item)
                for item in value
            ]
        elif isinstance(value, dict):
            serialized[key] = serialize_doc(value)
        else:
            serialized[key] = value
    return serialized

def _public_case_fields(case: dict) -> dict:
    allowed = {
        "id",
        "title",
        "type",
        "theme",
        "content",
        "source_material",
        "author",
        "department",
        "status",
        "created_at",
        "updated_at",
        "submitted_at",
        "review_at",
        "display_at",
        "view_count",
        "like_count",
        "is_hidden",
        "keywords",
    }
    return {key: case.get(key) for key in allowed if key in case}

def _public_case_list_fields(case: dict) -> dict:
    serialized = _public_case_fields(case)
    serialized.pop("content", None)
    serialized.pop("source_material", None)
    return serialized

def _apply_reviewed_version_snapshot(case: dict) -> dict:
    snapshot = dict(case)
    reviewed_version_id = snapshot.get("reviewed_version_id")
    if not reviewed_version_id:
        return snapshot

    try:
        version_id = int(reviewed_version_id)
        case_id = int(snapshot.get("id") or 0)
    except (TypeError, ValueError):
        return snapshot

    version = get_db().versions.find_one(
        {"id": version_id, "case_id": case_id}
    )
    serialized_version = serialize_version(version)
    if not serialized_version:
        return snapshot

    for field in PUBLIC_REVIEW_SNAPSHOT_FIELDS:
        if field in serialized_version:
            snapshot[field] = serialized_version.get(field)
    return snapshot

def serialize_case(case: dict | None) -> dict | None:
    if case is None:
        return None

    case = serialize_doc(case) or {}
    case["source_material"] = str(case.get("source_material") or "")
    case["keywords"] = _normalize_keywords(case.get("keywords"))
    case["is_approved"] = bool(case.get("is_approved", False))
    case["is_in_library"] = bool(case.get("is_in_library", False))
    case["is_hidden"] = bool(case.get("is_hidden", False))
    case["view_count"] = int(case.get("view_count") or 0)
    case["like_count"] = int(case.get("like_count") or 0)
    case["ai_reviews"] = _normalize_ai_reviews(case.get("ai_reviews"))
    if case.get("status") == "draft":
        case["display_at"] = case.get("updated_at") or case.get("created_at")
    else:
        case["display_at"] = case.get("submitted_at") or case.get("created_at")
    return case

def serialize_case_list_item(case: dict | None) -> dict | None:
    serialized = serialize_case(case)
    if not serialized:
        return None
    serialized.pop("content", None)
    serialized.pop("source_material", None)
    return serialized

def serialize_public_case(case: dict | None) -> dict | None:
    serialized = serialize_case(case)
    if not serialized:
        return None
    serialized = _apply_reviewed_version_snapshot(serialized)
    return _public_case_fields(serialized)

def serialize_public_case_list_item(case: dict | None) -> dict | None:
    serialized = serialize_case(case)
    if not serialized:
        return None
    serialized = _apply_reviewed_version_snapshot(serialized)
    return _public_case_list_fields(serialized)

def serialize_version(version: dict | None) -> dict | None:
    serialized = serialize_doc(version)
    if not serialized:
        return None
    serialized.setdefault("title", "")
    serialized.setdefault("type", "")
    serialized.setdefault("theme", "")
    serialized.setdefault("content", "")
    serialized.setdefault("source_material", "")
    serialized.setdefault("author", "")
    serialized["keywords"] = _normalize_keywords(serialized.get("keywords"))
    serialized.setdefault("owner_username", "")
    serialized.setdefault("created_by", serialized.get("changed_by", ""))
    serialized.setdefault("paragraphs", split_paragraphs(serialized.get("content", "")))
    serialized.setdefault("ai_review", None)
    serialized.setdefault("admin_comments", [])
    if serialized.get("change_reason") == "Initial creation":
        serialized["change_reason"] = "初始创建"
    return serialized
