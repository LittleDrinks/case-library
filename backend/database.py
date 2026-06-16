#!/usr/bin/env python3
"""Compatibility API for the case library MongoDB data layer."""

# ruff: noqa: F401

from db.connection import get_db, get_db_connection, get_mongo_client, init_db
from db.constants import (
    AI_REVIEW_DATETIME_FIELDS,
    BEIJING_TZ,
    CASE_STATUSES,
    COUNTER_COLLECTIONS,
    DATETIME_FIELDS,
    MAX_QUERY_LIMIT,
    MONGODB_DB_NAME,
    MONGODB_TIMEOUT_MS,
    MONGODB_URI,
    PUBLIC_REVIEW_SNAPSHOT_FIELDS,
    REVIEW_STATUSES,
    SQLITE_DB_PATH,
    STATISTICS_CACHE_TTL_SECONDS,
    USER_ROLES,
    USER_STATUSES,
    VERSIONED_FIELDS,
)
from db.counters import (
    _insert_with_generated_id,
    _max_legacy_id,
    next_sequence,
    sync_all_counters,
    sync_counter,
)
from db.datetime import (
    _normalize_datetime_fields,
    format_beijing_datetime,
    normalize_to_beijing_datetime,
    serialize_datetime,
)
from db.validators import (
    _bounded_limit,
    _normalize_ai_reviews,
    _normalize_keywords,
    _normalize_review_status,
    _normalize_token_version,
    _normalize_user_role,
    _now,
    _validate_case_status,
    _validate_review_status,
    _validate_user_role,
    _validate_user_status,
)
from repositories.cases import (
    _apply_hidden_filter,
    _author_aliases,
    _case_list_filter,
    _values_differ,
    backfill_owner_username,
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
from repositories.reviews import get_reviews, review_case, submit_for_review
from repositories.users import (
    _serialize_user_doc,
    authenticate_user,
    change_user_password,
    clear_users,
    create_user,
    delete_user,
    get_user_by_username,
    get_users_count,
    hash_password,
    list_users,
    rename_user,
    serialize_user_public,
    set_user_password,
    update_user_fields,
    verify_password,
)
from repositories.versions import _latest_version_id, create_ai_review_version, get_case_versions
from serializers import (
    _apply_reviewed_version_snapshot,
    _public_case_fields,
    serialize_case,
    serialize_doc,
    serialize_public_case,
    serialize_version,
)
from services.public import (
    _public_field_matches,
    _public_query_cases,
    _statistics_cache,
    _statistics_cache_lock,
    _status_search_filter,
    filter_cases,
    get_latest_cases,
    get_recommendation_candidates,
    get_statistics,
    get_trending_cases,
    invalidate_statistics_cache,
    search_cases,
)
from services.reviews import (
    normalize_paragraph_comments,
    normalize_structured_ai_review,
    split_paragraphs,
)

if __name__ == "__main__":
    init_db()
