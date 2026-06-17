"""Case version repository helpers."""

from __future__ import annotations

from pymongo import DESCENDING

from backend.app.domains.cases.serializers import serialize_doc, serialize_version
from backend.app.domains.reviews.helpers import normalize_structured_ai_review, split_paragraphs
from backend.db.connection import get_db
from backend.db.counters import _insert_with_generated_id
from backend.db.datetime import _normalize_datetime_fields
from backend.db.transactions import multi_collection_write
from backend.db.validators import _normalize_keywords, _now


class _CaseReviewUpdateConflictError(Exception):
    """The case changed or disappeared before the AI review pointer update."""


def _latest_version_id(case_id: int) -> int | None:
    version = get_db().versions.find_one(
        {"case_id": int(case_id)}, sort=[("version_number", DESCENDING)], projection={"id": 1}
    )
    return int(version["id"]) if version and version.get("id") is not None else None

def create_ai_review_version(
    case_id: int,
    reviewer: str,
    ai_review: dict,
    model: str = "",
    raw_answer: str = "",
    case_snapshot: dict | None = None,
) -> dict | None:
    db = get_db()
    current = case_snapshot or db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
    if not current:
        return None

    paragraphs = split_paragraphs(current.get("content", ""))
    paragraph_ids = {item["paragraph_id"] for item in paragraphs}
    normalized_review = normalize_structured_ai_review(ai_review, paragraph_ids)
    now = _now()

    max_version = db.versions.find_one(
        {"case_id": int(case_id)},
        sort=[("version_number", DESCENDING)],
        projection={"version_number": 1},
    )
    new_version = int(max_version["version_number"]) + 1 if max_version else 1
    version_doc = {
        "case_id": int(case_id),
        "version_number": new_version,
        "title": current.get("title", ""),
        "type": current.get("type", ""),
        "theme": current.get("theme", ""),
        "content": current.get("content", ""),
        "source_material": current.get("source_material", ""),
        "author": current.get("author", ""),
        "department": current.get("department", ""),
        "keywords": _normalize_keywords(current.get("keywords")),
        "owner_username": current.get("owner_username", ""),
        "created_by": reviewer,
        "paragraphs": paragraphs,
        "ai_review": {
            **normalized_review,
            "model": model,
            "raw_answer": raw_answer,
            "created_at": now,
            "created_by": reviewer,
        },
        "admin_comments": [],
        "changed_by": reviewer,
        "change_reason": "AI pre-submit review",
        "created_at": now,
    }
    try:
        with multi_collection_write("create_ai_review_version") as scope:
            version_id = _insert_with_generated_id("versions", version_doc)
            scope.compensate_with(lambda: db.versions.delete_one({"id": version_id}))
            update_filter = {"id": int(case_id), "status": current.get("status", {"$ne": "deleted"})}
            if current.get("updated_at") is not None:
                update_filter["updated_at"] = current.get("updated_at")
            else:
                update_filter.update(
                    {
                        "title": current.get("title", ""),
                        "type": current.get("type", ""),
                        "theme": current.get("theme", ""),
                        "content": current.get("content", ""),
                        "source_material": current.get("source_material", ""),
                    }
                )
            result = db.cases.update_one(
                update_filter,
                {
                    "$set": _normalize_datetime_fields(
                        {
                            "latest_review_version_id": version_id,
                            "updated_at": now,
                            "ai_reviews": [
                                {
                                    "prompt_id": "alpha/paragraph-review",
                                    "name": "AI 段落审核",
                                    "answer": raw_answer,
                                    "parsed": normalized_review,
                                    "parse_error": None,
                                    "reviewed_at": now,
                                }
                            ],
                        }
                    )
                },
            )
            if result.matched_count != 1 or result.modified_count != 1:
                raise _CaseReviewUpdateConflictError
    except _CaseReviewUpdateConflictError:
        return None
    return serialize_doc(db.versions.find_one({"id": version_id}))

def get_case_versions(case_id: int) -> list[dict]:
    cursor = get_db().versions.find({"case_id": int(case_id)}).sort("version_number", DESCENDING)
    return [item for item in (serialize_version(row) for row in cursor) if item is not None]
