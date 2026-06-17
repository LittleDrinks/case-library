"""Validation and normalization helpers for database inputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.db.constants import (
    AI_REVIEW_DATETIME_FIELDS,
    CASE_STATUSES,
    MAX_QUERY_LIMIT,
    REVIEW_STATUSES,
    USER_ROLES,
    USER_STATUSES,
)
from backend.db.datetime import format_beijing_datetime


def _now() -> str:
    """Return the current UTC+8 wall-clock time as a plain string."""
    return str(format_beijing_datetime(datetime.now(UTC)))

def _bounded_limit(limit: Any, default: int = 50) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(0, min(value, MAX_QUERY_LIMIT))

def _validate_case_status(status: str | None):
    if status is not None and status not in CASE_STATUSES:
        raise ValueError(f"Invalid case status: {status}")

def _validate_review_status(status: str | None):
    if status is not None and status not in REVIEW_STATUSES:
        raise ValueError(f"Invalid review status: {status}")

def _validate_user_role(role: str | None):
    if role is not None and role not in USER_ROLES:
        raise ValueError(f"Invalid user role: {role}")

def _normalize_user_role(role: str | None) -> str:
    if role == "user":
        return "normal"
    return role or "normal"

def _normalize_token_version(value: Any) -> int:
    try:
        version = int(value)
    except (TypeError, ValueError):
        return 0
    return max(version, 0)

def _validate_user_status(status: str | None):
    if status is not None and status not in USER_STATUSES:
        raise ValueError(f"Invalid user status: {status}")

def _normalize_review_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in ("approve", "approved"):
        return "approved"
    if normalized in ("reject", "rejected", "needs_revision"):
        return "rejected"
    if normalized == "pending":
        return "pending"
    raise ValueError(f"Invalid review status: {status}")

def _normalize_keywords(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    if isinstance(value, str):
        if not value:
            return []
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None and str(item) != ""]
        except json.JSONDecodeError:
            pass
        return [value]
    return [str(value)]

def _normalize_ai_reviews(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("ai_reviews must be valid JSON") from exc
    if not isinstance(value, list):
        raise ValueError("ai_reviews must be a list")
    if len(value) > 3:
        raise ValueError("ai_reviews cannot contain more than 3 records")

    normalized: list[dict[str, Any]] = []
    for item in value[-3:]:
        if not isinstance(item, dict):
            raise ValueError("ai_reviews records must be objects")
        record: dict[str, Any] = {
            "prompt_id": str(item.get("prompt_id", "")).strip(),
            "name": str(item.get("name", "")).strip(),
            "answer": str(item.get("answer", "")),
            "parse_error": item.get("parse_error"),
            "reviewed_at": item.get("reviewed_at") or _now(),
        }
        parsed = item.get("parsed")
        if isinstance(parsed, (dict, list, str, int, float, bool)) or parsed is None:
            record["parsed"] = parsed
        else:
            record["parsed"] = None
        for field in AI_REVIEW_DATETIME_FIELDS:
            if field in record:
                record[field] = format_beijing_datetime(record[field])
        if not record["prompt_id"]:
            raise ValueError("ai_reviews records require prompt_id")
        normalized.append(record)
    return normalized
