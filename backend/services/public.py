"""Public case listing, search, and statistics helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, cast

from pymongo import DESCENDING

from backend.app.domains.cases.serializers import (
    _public_case_fields,
    serialize_case,
    serialize_public_case,
    serialize_version,
)
from backend.db.connection import get_db
from backend.db.constants import PUBLIC_REVIEW_SNAPSHOT_FIELDS, STATISTICS_CACHE_TTL_SECONDS
from backend.db.validators import _bounded_limit, _validate_case_status
from backend.services.cache import invalidate_public_read_caches, public_read_cache

_statistics_cache: dict[str, Any] = {"expires_at": None, "data": None}
_statistics_cache_lock = RLock()
_STATISTICS_CACHE_KEY = "statistics"

def invalidate_statistics_cache() -> None:
    invalidate_public_read_caches("statistics")
    with _statistics_cache_lock:
        _statistics_cache["expires_at"] = None
        _statistics_cache["data"] = None

def _public_keyword_filter(query: str) -> dict[str, Any]:
    needle = query.strip()
    if not needle:
        return {}
    return {
        "$or": [
            {"title": {"$regex": needle, "$options": "i"}},
            {"content": {"$regex": needle, "$options": "i"}},
            {"source_material": {"$regex": needle, "$options": "i"}},
            {"keywords": {"$regex": needle, "$options": "i"}},
        ]
    }

def _public_text_filter(query: str) -> dict[str, Any]:
    needle = query.strip()
    if not needle:
        return {}
    if any(char.isspace() for char in needle):
        escaped = needle.replace('"', '\\"')
        needle = f'"{escaped}"'
    return {"$text": {"$search": needle}}

def _contains_cjk(query: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in query)

def _public_snapshot_overlay_stage() -> dict[str, Any]:
    return {
        "$addFields": {
            field: {
                "$cond": [
                    {"$ne": [{"$type": f"$reviewed_version.{field}"}, "missing"]},
                    f"$reviewed_version.{field}",
                    f"${field}",
                ]
            }
            for field in PUBLIC_REVIEW_SNAPSHOT_FIELDS
        }
    }

def _public_cases_pipeline(
    *,
    match_filters: list[dict[str, Any]] | None = None,
    sort: dict[str, Any] | None = None,
    skip: int | None = None,
    limit: int | None = None,
    text_query: str | None = None,
) -> list[dict[str, Any]]:
    first_match = {**_status_search_filter("approved"), "is_hidden": {"$ne": True}}
    if text_query and text_query.strip():
        first_match.update(_public_text_filter(text_query))

    pipeline: list[dict[str, Any]] = [
        {"$match": first_match},
        {
            "$lookup": {
                "from": "versions",
                "let": {"reviewed_version_id": "$reviewed_version_id", "case_id": "$id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$id", "$$reviewed_version_id"]},
                                    {"$eq": ["$case_id", "$$case_id"]},
                                ]
                            }
                        }
                    },
                    {"$limit": 1},
                ],
                "as": "reviewed_version",
            }
        },
        {"$unwind": {"path": "$reviewed_version", "preserveNullAndEmptyArrays": True}},
        _public_snapshot_overlay_stage(),
        {
            "$addFields": {
                "engagement_score": {
                    "$add": [
                        {"$ifNull": ["$view_count", 0]},
                        {"$ifNull": ["$like_count", 0]},
                    ]
                }
            }
        },
    ]
    if text_query and text_query.strip():
        pipeline.append({"$addFields": {"public_text_score": {"$meta": "textScore"}}})
    for match_filter in match_filters or []:
        if match_filter:
            pipeline.append({"$match": match_filter})
    if sort:
        pipeline.append({"$sort": sort})
    if skip is not None:
        pipeline.append({"$skip": max(0, int(skip))})
    if limit is not None:
        pipeline.append({"$limit": _bounded_limit(limit)})
    return pipeline

def _serialize_public_joined_case(row: dict | None) -> dict | None:
    case = serialize_case(row)
    if not case:
        return None

    reviewed_version = case.pop("reviewed_version", None)
    serialized_version = (
        serialize_version(reviewed_version) if isinstance(reviewed_version, dict) else None
    )
    if serialized_version:
        for field in PUBLIC_REVIEW_SNAPSHOT_FIELDS:
            if field in serialized_version:
                case[field] = serialized_version.get(field)

    return _public_case_fields(case)

def _public_query_cases(
    *,
    match_filters: list[dict[str, Any]] | None = None,
    sort: dict[str, Any] | None = None,
    skip: int | None = None,
    limit: int | None = None,
    text_query: str | None = None,
) -> list[dict]:
    pipeline = _public_cases_pipeline(
        match_filters=match_filters,
        sort=sort or {"created_at": DESCENDING},
        skip=skip,
        limit=limit,
        text_query=text_query,
    )
    return [
        item
        for item in (_serialize_public_joined_case(row) for row in get_db().cases.aggregate(pipeline))
        if item is not None
    ]

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

    needle = query.strip()
    bounded = _bounded_limit(limit, default=20)
    text_results = _public_query_cases(
        match_filters=[_public_keyword_filter(needle)],
        text_query=needle,
        sort={"public_text_score": {"$meta": "textScore"}, "created_at": DESCENDING},
        skip=offset,
        limit=bounded,
    )
    if text_results and not _contains_cjk(needle):
        return text_results

    return _public_query_cases(
        match_filters=[_public_keyword_filter(needle)],
        sort={"created_at": DESCENDING},
        skip=offset,
        limit=bounded,
    )

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

    match_filters: list[dict[str, Any]] = []
    if type_filter:
        match_filters.append({"type": type_filter})
    if theme_filter:
        match_filters.append({"theme": theme_filter})
    if keyword_filter:
        needle = keyword_filter.strip()
        if needle:
            text_results = _public_query_cases(
                match_filters=[*match_filters, _public_keyword_filter(needle)],
                text_query=needle,
                sort={"public_text_score": {"$meta": "textScore"}, "created_at": DESCENDING},
                skip=offset,
                limit=limit,
            )
            if text_results and not _contains_cjk(needle):
                return text_results
            match_filters = [*match_filters, _public_keyword_filter(needle)]

    return _public_query_cases(
        match_filters=match_filters,
        sort={"created_at": DESCENDING},
        skip=offset,
        limit=limit,
    )

def get_recommendation_candidates(case_id: int, limit: int = 5) -> list[dict]:
    from backend.repositories.cases import get_case

    current_case = serialize_public_case(get_case(case_id))
    if not current_case:
        return []

    bounded = _bounded_limit(limit, default=5)
    return _public_query_cases(
        match_filters=[
            {
                "id": {"$ne": int(case_id)},
                "$or": [
                    {"type": current_case.get("type")},
                    {"theme": current_case.get("theme")},
                ],
            }
        ],
        sort={"engagement_score": DESCENDING},
        limit=bounded,
    )

def get_trending_cases(limit: int = 10) -> list[dict]:
    return _public_query_cases(
        sort={"engagement_score": DESCENDING},
        limit=_bounded_limit(limit, default=10),
    )

def get_latest_cases(limit: int = 10) -> list[dict]:
    return _public_query_cases(
        sort={"created_at": DESCENDING},
        limit=_bounded_limit(limit, default=10),
    )

def get_statistics() -> dict:
    now = datetime.now(UTC)
    with _statistics_cache_lock:
        cached = _statistics_cache.get("data")
        expires_at = _statistics_cache.get("expires_at")
        if cached is not None and isinstance(expires_at, datetime) and expires_at > now:
            cached_copy = public_read_cache.get(_STATISTICS_CACHE_KEY) or cached
            return cast(
                dict,
                public_read_cache.set(
                    _STATISTICS_CACHE_KEY,
                    cached_copy,
                    STATISTICS_CACHE_TTL_SECONDS,
                ),
            )

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
        cached_stats = public_read_cache.set(
            _STATISTICS_CACHE_KEY,
            stats,
            STATISTICS_CACHE_TTL_SECONDS,
        )
        _statistics_cache["data"] = cached_stats
        _statistics_cache["expires_at"] = now + timedelta(
            seconds=max(0, STATISTICS_CACHE_TTL_SECONDS)
        )
        return cast(dict, cached_stats)
