"""Public case listing, search, and statistics helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any

from db.connection import get_db
from db.constants import PUBLIC_REVIEW_SNAPSHOT_FIELDS, STATISTICS_CACHE_TTL_SECONDS
from db.validators import _bounded_limit, _validate_case_status
from pymongo import DESCENDING
from serializers import (
    _public_case_fields,
    serialize_case,
    serialize_public_case,
    serialize_version,
)

_statistics_cache: dict[str, Any] = {"expires_at": None, "data": None}
_statistics_cache_lock = RLock()

def invalidate_statistics_cache() -> None:
    with _statistics_cache_lock:
        _statistics_cache["expires_at"] = None
        _statistics_cache["data"] = None

def _public_query_cases() -> list[dict]:
    cursor = (
        get_db()
        .cases.find({**_status_search_filter("approved"), "is_hidden": {"$ne": True}})
        .sort("created_at", DESCENDING)
    )
    cases = [serialize_case(row) for row in cursor]

    # Batch fetch reviewed versions to avoid N+1 queries per public listing
    version_ids = []
    case_version_map: dict[int, list[dict]] = {}
    for case in cases:
        reviewed_version_id = case.get("reviewed_version_id")
        if reviewed_version_id:
            try:
                version_id = int(reviewed_version_id)
                version_ids.append(version_id)
                case_version_map.setdefault(version_id, []).append(case)
            except (TypeError, ValueError):
                pass

    if version_ids:
        for version in get_db().versions.find({"id": {"$in": version_ids}}):
            serialized_version = serialize_version(version)
            if not serialized_version:
                continue
            version_id = serialized_version.get("id")
            if version_id is None:
                continue
            for case in case_version_map.get(version_id, []):
                for field in PUBLIC_REVIEW_SNAPSHOT_FIELDS:
                    if field in serialized_version:
                        case[field] = serialized_version.get(field)

    return [item for item in (_public_case_fields(case) for case in cases) if item is not None]

def _public_field_matches(item: dict, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    searchable = [
        str(item.get("title") or ""),
        str(item.get("content") or ""),
        str(item.get("source_material") or ""),
        " ".join(str(value) for value in item.get("keywords") or []),
    ]
    return any(needle in value.lower() for value in searchable)

def _status_search_filter(status: str | None) -> dict[str, Any]:
    if not status or status in ("all", "approved", "approved_all"):
        return {"status": "approved"}
    if status in ("draft", "pending_review", "rejected", "needs_revision"):
        return {"status": "__public_search_no_match__"}
    _validate_case_status(status)
    return {"status": "__public_search_no_match__"}

def search_cases(
    query: str,
    status: str | None = "approved",
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    if not query or not query.strip():
        return []

    if _status_search_filter(status).get("status") != "approved":
        return []

    matches = [item for item in _public_query_cases() if _public_field_matches(item, query)]
    start = max(0, int(offset))
    end = start + _bounded_limit(limit, default=20)
    return matches[start:end]

def filter_cases(
    type_filter: str | None = None,
    theme_filter: str | None = None,
    status_filter: str = "approved",
    keyword_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    if _status_search_filter(status_filter).get("status") != "approved":
        return []

    matches = _public_query_cases()
    if type_filter:
        matches = [item for item in matches if item.get("type") == type_filter]
    if theme_filter:
        matches = [item for item in matches if item.get("theme") == theme_filter]
    if keyword_filter:
        matches = [item for item in matches if _public_field_matches(item, keyword_filter)]

    start = max(0, int(offset))
    end = start + _bounded_limit(limit)
    return matches[start:end]

def get_recommendation_candidates(case_id: int, limit: int = 5) -> list[dict]:
    from repositories.cases import get_case

    current_case = serialize_public_case(get_case(case_id))
    if not current_case:
        return []

    bounded = _bounded_limit(limit, default=5)
    cases = [
        item
        for item in _public_query_cases()
        if item.get("id") != int(case_id)
        and (item.get("type") == current_case.get("type") or item.get("theme") == current_case.get("theme"))
    ]
    cases.sort(key=lambda item: item.get("view_count", 0) + item.get("like_count", 0), reverse=True)
    return cases[:bounded]

def get_trending_cases(limit: int = 10) -> list[dict]:
    cases = _public_query_cases()
    cases.sort(key=lambda item: item.get("view_count", 0) + item.get("like_count", 0), reverse=True)
    return cases[:_bounded_limit(limit, default=10)]

def get_latest_cases(limit: int = 10) -> list[dict]:
    query = {**_status_search_filter("approved"), "is_hidden": {"$ne": True}}
    cursor = (
        get_db()
        .cases.find(query)
        .sort("created_at", DESCENDING)
        .limit(_bounded_limit(limit, default=10))
    )
    return [item for item in (serialize_public_case(row) for row in cursor) if item is not None]

def get_statistics() -> dict:
    now = datetime.now(UTC)
    with _statistics_cache_lock:
        cached = _statistics_cache.get("data")
        expires_at = _statistics_cache.get("expires_at")
        if cached is not None and isinstance(expires_at, datetime) and expires_at > now:
            return json.loads(json.dumps(cached))

        public_cases = _public_query_cases()

        stats: dict[str, Any] = {"total_cases": len(public_cases), "by_type": {}, "by_theme": {}}
        total_views = 0
        total_likes = 0
        for case in public_cases:
            case_type = case.get("type")
            if case_type is not None:
                stats["by_type"][case_type] = stats["by_type"].get(case_type, 0) + 1

            case_theme = case.get("theme")
            if case_theme is not None:
                stats["by_theme"][case_theme] = stats["by_theme"].get(case_theme, 0) + 1

            total_views += int(case.get("view_count") or 0)
            total_likes += int(case.get("like_count") or 0)

        stats["total_views"] = total_views
        stats["total_likes"] = total_likes
        _statistics_cache["data"] = json.loads(json.dumps(stats))
        _statistics_cache["expires_at"] = now + timedelta(seconds=max(0, STATISTICS_CACHE_TTL_SECONDS))
        return stats
