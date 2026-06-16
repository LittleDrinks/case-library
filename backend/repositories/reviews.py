"""Review repository helpers."""

from __future__ import annotations

from typing import Any

from db.connection import get_db
from db.counters import _insert_with_generated_id
from db.datetime import _normalize_datetime_fields
from db.validators import _normalize_review_status, _now
from pymongo import DESCENDING
from serializers import serialize_doc
from services.public import invalidate_statistics_cache
from services.reviews import normalize_paragraph_comments

from repositories.versions import _latest_version_id


def submit_for_review(case_id: int, version_id: int | None = None) -> bool:
    db = get_db()
    now = _now()
    bound_version_id = int(version_id) if version_id is not None else _latest_version_id(case_id)
    if bound_version_id is None:
        return False
    if not db.versions.find_one({"id": bound_version_id, "case_id": int(case_id)}):
        return False

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

    review_doc = {
        "case_id": int(case_id),
        "version_id": bound_version_id,
        "reviewer": "system",
        "comment": "Submitted for review",
        "paragraph_comments": [],
        "status": "pending",
        "review_at": _now(),
    }
    _insert_with_generated_id("reviews", review_doc)
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

    review_doc = {
        "case_id": int(case_id),
        "version_id": bound_version_id,
        "reviewer": reviewer,
        "comment": comment,
        "paragraph_comments": normalized_comments,
        "status": review_status,
        "review_at": _now(),
    }
    _insert_with_generated_id("reviews", review_doc)
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
    if case.get("status") == "approved" or new_status == "approved":
        invalidate_statistics_cache()
    return True

def get_reviews(case_id: int) -> list[dict]:
    cursor = get_db().reviews.find({"case_id": int(case_id)}).sort("review_at", DESCENDING)
    return [serialize_doc(row) for row in cursor]
