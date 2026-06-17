"""Review repository helpers."""

from __future__ import annotations

from typing import Any

from pymongo import DESCENDING

from backend.app.domains.cases.serializers import serialize_doc
from backend.app.domains.reviews.helpers import normalize_paragraph_comments
from backend.db.connection import get_db
from backend.db.counters import _insert_with_generated_id
from backend.db.datetime import _normalize_datetime_fields
from backend.db.transactions import multi_collection_write
from backend.db.validators import _normalize_review_status, _now
from backend.repositories.versions import _latest_version_id
from backend.services.public import invalidate_statistics_cache


def submit_for_review(case_id: int, version_id: int | None = None) -> bool:
    db = get_db()
    now = _now()
    latest_version_id = _latest_version_id(case_id)
    bound_version_id = int(version_id) if version_id is not None else latest_version_id
    if bound_version_id is None or latest_version_id is None:
        return False
    if bound_version_id != latest_version_id:
        return False
    if not db.versions.find_one({"id": bound_version_id, "case_id": int(case_id)}):
        return False

    with multi_collection_write("submit_case_for_review") as scope:
        case_before = db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
        result = db.cases.update_one(
            {"id": int(case_id), "status": {"$in": ["draft", "needs_revision"]}},
            {
                "$set": _normalize_datetime_fields(
                    {
                        "status": "pending_review",
                        "updated_at": now,
                        "submitted_at": now,
                        "submitted_version_id": bound_version_id,
                    }
                )
            },
        )
        if result.matched_count == 0 or result.modified_count == 0:
            return False
        if case_before:
            scope.compensate_with(lambda: db.cases.replace_one({"id": int(case_id)}, case_before))

        review_doc = {
            "case_id": int(case_id),
            "version_id": bound_version_id,
            "reviewer": "system",
            "comment": "Submitted for review",
            "paragraph_comments": [],
            "status": "pending",
            "review_at": _now(),
        }
        review_id = _insert_with_generated_id("reviews", review_doc)
        scope.compensate_with(lambda: db.reviews.delete_one({"id": review_id}))
    return True

def review_case(
    case_id: int,
    reviewer: str,
    comment: str,
    status: str,
    version_id: int | None = None,
    paragraph_comments: Any = None,
) -> bool:
    db = get_db()
    case = db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
    if not case:
        return False
    if case.get("status") != "pending_review":
        return False
    bound_version_id = int(version_id or case.get("submitted_version_id") or 0)
    if not bound_version_id:
        bound_version_id = _latest_version_id(case_id) or 0
    version = db.versions.find_one({"id": bound_version_id, "case_id": int(case_id)})
    if not version:
        return False
    paragraph_ids = {item.get("paragraph_id") for item in version.get("paragraphs", [])}
    normalized_comments = normalize_paragraph_comments(paragraph_comments or [], paragraph_ids)

    review_status = _normalize_review_status(status)
    if review_status == "approved":
        new_status = "approved"
        is_approved = True
        is_in_library = True
    elif review_status == "rejected":
        new_status = "needs_revision"
        is_approved = False
        is_in_library = False
    else:
        new_status = "pending_review"
        is_approved = False
        is_in_library = False

    with multi_collection_write("review_case") as scope:
        result = db.cases.update_one(
            {"id": int(case_id), "status": {"$ne": "deleted"}},
            {
                "$set": _normalize_datetime_fields(
                    {
                        "status": new_status,
                        "is_approved": is_approved,
                        "is_in_library": is_in_library,
                        "reviewed_version_id": bound_version_id,
                        "review_at": _now(),
                        "updated_at": _now(),
                    }
                )
            },
        )
        if result.matched_count == 0:
            return False
        scope.compensate_with(lambda: db.cases.replace_one({"id": int(case_id)}, case))

        review_doc = {
            "case_id": int(case_id),
            "version_id": bound_version_id,
            "reviewer": reviewer,
            "comment": comment,
            "paragraph_comments": normalized_comments,
            "status": review_status,
            "review_at": _now(),
        }
        review_id = _insert_with_generated_id("reviews", review_doc)
        scope.compensate_with(lambda: db.reviews.delete_one({"id": review_id}))
        if normalized_comments:
            existing = version.get("admin_comments") or []
            db.versions.update_one(
                {"id": bound_version_id},
                {
                    "$set": {
                        "admin_comments": [
                            *existing,
                            {
                                "reviewer": reviewer,
                                "status": review_status,
                                "comment": comment,
                                "created_at": _now(),
                                "comments": normalized_comments,
                            },
                        ]
                    }
                },
            )
            scope.compensate_with(
                lambda: db.versions.update_one(
                    {"id": bound_version_id},
                    {"$set": {"admin_comments": existing}},
                )
            )
    if case.get("status") == "approved" or new_status == "approved":
        invalidate_statistics_cache()
    return True

def get_reviews(case_id: int) -> list[dict]:
    cursor = get_db().reviews.find({"case_id": int(case_id)}).sort("review_at", DESCENDING)
    return [serialized for row in cursor if (serialized := serialize_doc(row)) is not None]
