#!/usr/bin/env python3
"""MongoDB data access layer for the case library."""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient, TEXT
from pymongo.errors import DuplicateKeyError


load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "case_library")
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))
SQLITE_DB_PATH = os.getenv(
    "SQLITE_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "cases.db"),
)

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS)
    return _client


def get_db_connection():
    """Compatibility wrapper: return the MongoDB database object."""
    return get_mongo_client()[MONGODB_DB_NAME]


def get_db():
    return get_db_connection()


def serialize_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value


def serialize_doc(doc: Optional[Dict]) -> Optional[Dict]:
    if doc is None:
        return None

    serialized: Dict[str, Any] = {}
    for key, value in doc.items():
        if isinstance(value, ObjectId):
            serialized[key] = str(value)
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


def _normalize_keywords(value: Any) -> List[str]:
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


def serialize_case(case: Optional[Dict]) -> Optional[Dict]:
    if case is None:
        return None

    case = serialize_doc(case) or {}
    case["keywords"] = _normalize_keywords(case.get("keywords"))
    case["is_approved"] = bool(case.get("is_approved", False))
    case["is_in_library"] = bool(case.get("is_in_library", False))
    case["view_count"] = int(case.get("view_count") or 0)
    case["like_count"] = int(case.get("like_count") or 0)
    return case


def _next_id(collection_name: str) -> int:
    db = get_db()
    last_doc = db[collection_name].find_one(
        {"id": {"$type": "number"}},
        sort=[("id", DESCENDING)],
        projection={"id": 1},
    )
    return int(last_doc["id"]) + 1 if last_doc and "id" in last_doc else 1


def _insert_with_generated_id(collection_name: str, doc: Dict) -> int:
    db = get_db()
    collection = db[collection_name]
    for _ in range(5):
        doc["id"] = _next_id(collection_name)
        try:
            collection.insert_one(doc)
            return int(doc["id"])
        except DuplicateKeyError:
            continue
    raise RuntimeError(f"Unable to allocate id for {collection_name}")


def _now() -> datetime:
    return datetime.now()


def init_db():
    """Initialize MongoDB indexes. This never drops data."""
    db = get_db()
    get_mongo_client().admin.command("ping")

    db.users.create_index([("username", ASCENDING)], unique=True)

    db.cases.create_index([("id", ASCENDING)], unique=True)
    db.cases.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.cases.create_index([("author", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)])
    db.cases.create_index([("type", ASCENDING), ("theme", ASCENDING)])
    db.cases.create_index(
        [("title", TEXT), ("content", TEXT), ("keywords", TEXT)],
        name="cases_text_idx",
        default_language="none",
    )

    db.reviews.create_index([("case_id", ASCENDING), ("review_at", DESCENDING)])
    db.versions.create_index([("case_id", ASCENDING), ("version_number", DESCENDING)])
    db.deployments.create_index([("case_id", ASCENDING), ("deployed_at", DESCENDING)])

    print(f"MongoDB initialized: {MONGODB_URI}/{MONGODB_DB_NAME}")


def get_user_by_username(username: str) -> Optional[Dict]:
    user = get_db().users.find_one({"username": username})
    return serialize_doc(user)


def create_user(username: str, password_hash: str, role: str = "user") -> int:
    doc = {
        "username": username,
        "password": password_hash,
        "role": role,
        "created_at": _now(),
    }
    return _insert_with_generated_id("users", doc)


def get_users_count() -> int:
    return get_db().users.count_documents({})


def create_case(case_data: Dict) -> int:
    now = _now()
    doc = {
        "title": case_data.get("title", ""),
        "type": case_data.get("type", ""),
        "theme": case_data.get("theme", ""),
        "content": case_data.get("content", ""),
        "status": case_data.get("status", "draft"),
        "author": case_data.get("author", ""),
        "department": case_data.get("department", ""),
        "keywords": _normalize_keywords(case_data.get("keywords", [])),
        "created_at": case_data.get("created_at") or now,
        "updated_at": case_data.get("updated_at") or now,
        "is_approved": bool(case_data.get("is_approved", False)),
        "is_in_library": bool(case_data.get("is_in_library", False)),
        "view_count": int(case_data.get("view_count") or 0),
        "like_count": int(case_data.get("like_count") or 0),
    }

    if case_data.get("deployed_at") is not None:
        doc["deployed_at"] = case_data.get("deployed_at")
    if case_data.get("deployed_by") is not None:
        doc["deployed_by"] = case_data.get("deployed_by")

    case_id = _insert_with_generated_id("cases", doc)

    version_doc = {
        "case_id": case_id,
        "version_number": 1,
        "content": doc.get("content", ""),
        "changed_by": doc.get("author", ""),
        "change_reason": "Initial creation",
        "created_at": now,
    }
    _insert_with_generated_id("versions", version_doc)

    return case_id


def get_case(case_id: int, include_deleted: bool = False) -> Optional[Dict]:
    query: Dict[str, Any] = {"id": int(case_id)}
    if not include_deleted:
        query["status"] = {"$ne": "deleted"}

    case = get_db().cases.find_one(query)
    return serialize_case(case)


def _case_list_filter(
    status: Optional[str] = None,
    author: Optional[str] = None,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {}

    if author:
        query["author"] = author

    if status and status not in ("all", ""):
        if status == "rejected":
            query["status"] = "needs_revision"
        elif status in ("approved", "approved_all"):
            query["status"] = {"$in": ["approved", "approved_pending_deploy"]}
        else:
            query["status"] = status
    elif not author:
        query["status"] = {"$nin": ["draft", "deleted"]}

    if not include_deleted:
        existing_status = query.get("status")
        if existing_status is None:
            query["status"] = {"$ne": "deleted"}
        elif isinstance(existing_status, dict):
            existing_status.setdefault("$ne", "deleted")
        elif existing_status == "deleted":
            query["status"] = {"$ne": "deleted"}

    return query


def get_all_cases(
    status: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    author: Optional[str] = None,
) -> List[Dict]:
    db = get_db()
    query = _case_list_filter(status=status, author=author)
    cursor = (
        db.cases.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, int(offset)))
        .limit(max(0, int(limit)))
    )
    return [serialize_case(row) for row in cursor]


def count_cases(status: Optional[str] = None, author: Optional[str] = None) -> int:
    return get_db().cases.count_documents(_case_list_filter(status=status, author=author))


def update_case(case_id: int, case_data: Dict, updated_by: str = "system", change_reason: str = "") -> bool:
    db = get_db()
    current = db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
    if not current:
        return False

    allowed_fields = [
        "title",
        "type",
        "theme",
        "content",
        "author",
        "department",
        "status",
        "is_approved",
        "is_in_library",
    ]
    updates = {field: case_data[field] for field in allowed_fields if field in case_data}

    if "keywords" in case_data:
        updates["keywords"] = _normalize_keywords(case_data.get("keywords"))

    updates["updated_at"] = _now()

    result = db.cases.update_one({"id": int(case_id)}, {"$set": updates})
    if result.matched_count == 0:
        return False

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
        "content": (updated or {}).get("content", ""),
        "changed_by": updated_by,
        "change_reason": change_reason,
        "created_at": _now(),
    }
    _insert_with_generated_id("versions", version_doc)

    return True


def delete_case(case_id: int) -> Dict:
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

    result = db.cases.update_one(
        {"id": int(case_id)},
        {"$set": {"status": "deleted", "is_in_library": False, "updated_at": _now()}},
    )

    return {
        "success": result.modified_count > 0,
        "was_in_library": bool(case.get("is_in_library", False)),
        "view_count": int(case.get("view_count") or 0),
        "like_count": int(case.get("like_count") or 0),
        "type": case.get("type"),
        "theme": case.get("theme"),
    }


def submit_for_review(case_id: int) -> bool:
    db = get_db()
    if not db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}}):
        return False

    result = db.cases.update_one(
        {"id": int(case_id)},
        {"$set": {"status": "pending_review", "updated_at": _now()}},
    )
    if result.matched_count == 0:
        return False

    review_doc = {
        "case_id": int(case_id),
        "reviewer": "system",
        "comment": "Submitted for review",
        "status": "pending",
        "review_at": _now(),
    }
    _insert_with_generated_id("reviews", review_doc)
    return True


def review_case(case_id: int, reviewer: str, comment: str, status: str) -> bool:
    db = get_db()
    if not db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}}):
        return False

    normalized = (status or "").strip().lower()
    if normalized in ("approve", "approved"):
        new_status = "approved"
        is_approved = True
        is_in_library = True
    elif normalized in ("reject", "rejected", "needs_revision"):
        new_status = "needs_revision"
        is_approved = False
        is_in_library = False
    elif normalized == "pending":
        new_status = "pending_review"
        is_approved = False
        is_in_library = False
    else:
        return False

    result = db.cases.update_one(
        {"id": int(case_id)},
        {
            "$set": {
                "status": new_status,
                "is_approved": is_approved,
                "is_in_library": is_in_library,
                "updated_at": _now(),
            }
        },
    )
    if result.matched_count == 0:
        return False

    review_doc = {
        "case_id": int(case_id),
        "reviewer": reviewer,
        "comment": comment,
        "status": status,
        "review_at": _now(),
    }
    _insert_with_generated_id("reviews", review_doc)
    return True


def get_case_versions(case_id: int) -> List[Dict]:
    cursor = get_db().versions.find({"case_id": int(case_id)}).sort("version_number", DESCENDING)
    return [serialize_doc(row) for row in cursor]


def get_reviews(case_id: int) -> List[Dict]:
    cursor = get_db().reviews.find({"case_id": int(case_id)}).sort("review_at", DESCENDING)
    return [serialize_doc(row) for row in cursor]


def increment_view_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$inc": {"view_count": 1}},
    )
    return result.matched_count > 0


def increment_like_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$inc": {"like_count": 1}},
    )
    return result.matched_count > 0


def decrement_like_count(case_id: int) -> bool:
    db = get_db()
    result = db.cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}, "like_count": {"$gt": 0}},
        {"$inc": {"like_count": -1}},
    )
    if result.matched_count > 0:
        return True
    return db.cases.count_documents({"id": int(case_id), "status": {"$ne": "deleted"}}) > 0


def _status_search_filter(status: Optional[str]) -> Dict[str, Any]:
    if not status or status == "all":
        return {"status": {"$ne": "deleted"}}
    if status in ("approved", "approved_all"):
        return {"status": {"$in": ["approved", "approved_pending_deploy"]}}
    if status == "rejected":
        return {"status": "needs_revision"}
    return {"status": status}


def search_cases(
    query: str,
    status: Optional[str] = "approved",
    limit: int = 20,
    offset: int = 0,
) -> List[Dict]:
    if not query or not query.strip():
        return []

    escaped = re.escape(query.strip())
    regex = {"$regex": escaped, "$options": "i"}
    mongo_query: Dict[str, Any] = {
        **_status_search_filter(status),
        "$or": [
            {"title": regex},
            {"content": regex},
            {"keywords": regex},
        ],
    }

    cursor = (
        get_db().cases.find(mongo_query)
        .sort("created_at", DESCENDING)
        .skip(max(0, int(offset)))
        .limit(max(0, int(limit)))
    )
    return [serialize_case(row) for row in cursor]


def filter_cases(
    type_filter: Optional[str] = None,
    theme_filter: Optional[str] = None,
    status_filter: str = "approved",
    keyword_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict]:
    query = _status_search_filter(status_filter)
    if type_filter:
        query["type"] = type_filter
    if theme_filter:
        query["theme"] = theme_filter
    if keyword_filter:
        regex = {"$regex": re.escape(keyword_filter), "$options": "i"}
        query["$or"] = [{"title": regex}, {"content": regex}, {"keywords": regex}]

    cursor = (
        get_db().cases.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, int(offset)))
        .limit(max(0, int(limit)))
    )
    return [serialize_case(row) for row in cursor]


def get_recommendation_candidates(case_id: int, limit: int = 5) -> List[Dict]:
    current_case = get_case(case_id)
    if not current_case:
        return []

    query = {
        "id": {"$ne": int(case_id)},
        "status": {"$in": ["approved", "approved_pending_deploy"]},
        "$or": [
            {"type": current_case.get("type")},
            {"theme": current_case.get("theme")},
        ],
    }
    cursor = get_db().cases.find(query).limit(max(0, int(limit) * 3))
    cases = [serialize_case(row) for row in cursor]
    cases.sort(key=lambda item: (item.get("view_count", 0) + item.get("like_count", 0)), reverse=True)
    return cases[:limit]


def get_trending_cases(limit: int = 10) -> List[Dict]:
    cursor = get_db().cases.find(_status_search_filter("approved"))
    cases = [serialize_case(row) for row in cursor]
    cases.sort(key=lambda item: (item.get("view_count", 0) + item.get("like_count", 0)), reverse=True)
    return cases[:limit]


def get_latest_cases(limit: int = 10) -> List[Dict]:
    cursor = get_db().cases.find(_status_search_filter("approved")).sort("created_at", DESCENDING).limit(max(0, int(limit)))
    return [serialize_case(row) for row in cursor]


def get_statistics() -> Dict:
    db = get_db()
    approved_filter = {"status": {"$in": ["approved", "approved_pending_deploy"]}}

    stats: Dict[str, Any] = {}
    stats["total_cases"] = db.cases.count_documents(approved_filter)

    stats["by_type"] = {
        row["_id"]: row["count"]
        for row in db.cases.aggregate(
            [{"$match": approved_filter}, {"$group": {"_id": "$type", "count": {"$sum": 1}}}]
        )
        if row.get("_id") is not None
    }
    stats["by_theme"] = {
        row["_id"]: row["count"]
        for row in db.cases.aggregate(
            [{"$match": approved_filter}, {"$group": {"_id": "$theme", "count": {"$sum": 1}}}]
        )
        if row.get("_id") is not None
    }

    totals = list(
        db.cases.aggregate(
            [
                {"$match": approved_filter},
                {
                    "$group": {
                        "_id": None,
                        "total_views": {"$sum": {"$ifNull": ["$view_count", 0]}},
                        "total_likes": {"$sum": {"$ifNull": ["$like_count", 0]}},
                    }
                },
            ]
        )
    )
    stats["total_views"] = int(totals[0]["total_views"]) if totals else 0
    stats["total_likes"] = int(totals[0]["total_likes"]) if totals else 0
    return stats


if __name__ == "__main__":
    init_db()
