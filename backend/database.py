#!/usr/bin/env python3
"""MongoDB data access layer for the case library."""

import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "case_library")
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))
SQLITE_DB_PATH = os.getenv(
    "SQLITE_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "cases.db"),
)

CASE_STATUSES = {
    "draft",
    "pending_review",
    "approved",
    "needs_revision",
    "deleted",
}
REVIEW_STATUSES = {"pending", "approved", "rejected", "approve", "reject", "needs_revision"}
USER_ROLES = {"normal", "admin"}
USER_STATUSES = {"active", "no_active"}
COUNTER_COLLECTIONS = ["users", "cases", "reviews", "versions", "deployments"]
MAX_QUERY_LIMIT = 100
VERSIONED_FIELDS = [
    "title",
    "type",
    "theme",
    "content",
    "source_material",
    "author",
    "department",
    "keywords",
]
PUBLIC_REVIEW_SNAPSHOT_FIELDS = [
    "title",
    "type",
    "theme",
    "content",
    "source_material",
    "author",
    "department",
    "keywords",
]
DATETIME_FIELDS = {
    "created_at",
    "updated_at",
    "submitted_at",
    "review_at",
    "deployed_at",
    "deleted_at",
}
AI_REVIEW_DATETIME_FIELDS = {"reviewed_at", "created_at"}
BEIJING_TZ = timezone(timedelta(hours=8))

_client: MongoClient | None = None


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


def normalize_to_beijing_datetime(value: Any) -> Any:
    """Normalize datetime-like values to a naive UTC+8 wall-clock datetime.

    PyMongo reads BSON dates as naive UTC datetimes by default. Plain strings
    without timezone metadata are treated as already being Beijing wall time.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(BEIJING_TZ).replace(tzinfo=None)
        return value.replace(tzinfo=UTC).astimezone(BEIJING_TZ).replace(tzinfo=None)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value

        parse_text = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(parse_text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    parsed = None
            if parsed is None:
                return value

        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return normalize_to_beijing_datetime(parsed)
        return parsed.replace(tzinfo=None)

    return value


def format_beijing_datetime(value: Any) -> Any:
    normalized = normalize_to_beijing_datetime(value)
    if isinstance(normalized, datetime):
        return normalized.strftime("%Y-%m-%d %H:%M:%S")
    return normalized


def _normalize_datetime_fields(doc: dict[str, Any]) -> dict[str, Any]:
    for field in DATETIME_FIELDS:
        if field in doc:
            doc[field] = format_beijing_datetime(doc[field])
    return doc


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


COMMENT_CATEGORIES = {"source", "fact", "structure", "classification", "classroom", "clarity"}
COMMENT_SEVERITIES = {"info", "suggestion", "important"}


def split_paragraphs(content: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    for line in str(content or "").splitlines():
        text = line.strip()
        if not text:
            continue
        paragraphs.append({"paragraph_id": f"p{len(paragraphs) + 1}", "text": text})
    if not paragraphs and str(content or "").strip():
        paragraphs.append({"paragraph_id": "p1", "text": str(content).strip()})
    return paragraphs


def _normalize_summary(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        value = {}
    summary: dict[str, list[str]] = {}
    for key in ("strengths", "risks", "suggested_next_steps"):
        items = value.get(key, [])
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            items = []
        summary[key] = [str(item) for item in items if item is not None and str(item).strip()]
    return summary


def normalize_paragraph_comments(value: Any, paragraph_ids: set[str] | None = None) -> list[dict]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("paragraph_comments must be valid JSON") from exc
    if not isinstance(value, list):
        raise ValueError("paragraph_comments must be a list")

    normalized: list[dict[str, Any]] = []
    allowed_ids = paragraph_ids or set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError("paragraph_comments records must be objects")
        paragraph_id = str(item.get("paragraph_id", "")).strip()
        if not paragraph_id:
            raise ValueError("paragraph_comments records require paragraph_id")
        if allowed_ids and paragraph_id not in allowed_ids:
            raise ValueError(f"Unknown paragraph_id: {paragraph_id}")

        category = str(item.get("category", "clarity")).strip()
        if category not in COMMENT_CATEGORIES:
            category = "clarity"
        severity = str(item.get("severity", "suggestion")).strip()
        if severity not in COMMENT_SEVERITIES:
            severity = "suggestion"
        message = str(item.get("message", "")).strip()
        if not message:
            raise ValueError("paragraph_comments records require message")

        normalized.append(
            {
                "id": str(item.get("id") or f"c{index + 1}"),
                "paragraph_id": paragraph_id,
                "quote": str(item.get("quote", ""))[:500],
                "category": category,
                "severity": severity,
                "message": message,
                "suggestion": str(item.get("suggestion", "")).strip(),
            }
        )
    return normalized


def normalize_structured_ai_review(value: Any, paragraph_ids: set[str]) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("AI review JSON parse failed") from exc
    if not isinstance(value, dict):
        raise ValueError("AI review result must be a JSON object")

    comments = normalize_paragraph_comments(value.get("comments", []), paragraph_ids)
    return {"comments": comments, "summary": _normalize_summary(value.get("summary", {}))}


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


def serialize_public_case(case: dict | None) -> dict | None:
    serialized = serialize_case(case)
    if not serialized:
        return None
    serialized = _apply_reviewed_version_snapshot(serialized)
    return _public_case_fields(serialized)


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


def _now() -> str:
    """Return the current UTC+8 wall-clock time as a plain string."""
    return format_beijing_datetime(datetime.now(UTC))


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


def _serialize_user_doc(user: dict | None) -> dict | None:
    serialized = serialize_doc(user)
    if serialized:
        serialized["role"] = _normalize_user_role(serialized.get("role"))
        serialized.setdefault("nickname", "")
        serialized.setdefault("status", "active")
        serialized["must_change_password"] = bool(serialized.get("must_change_password", False))
        serialized["token_version"] = _normalize_token_version(serialized.get("token_version"))
    return serialized


def _validate_user_status(status: str | None):
    if status is not None and status not in USER_STATUSES:
        raise ValueError(f"Invalid user status: {status}")


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _normalize_review_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in ("approve", "approved"):
        return "approved"
    if normalized in ("reject", "rejected", "needs_revision"):
        return "rejected"
    if normalized == "pending":
        return "pending"
    raise ValueError(f"Invalid review status: {status}")


def _max_legacy_id(collection_name: str) -> int:
    doc = get_db()[collection_name].find_one(
        {"id": {"$type": "number"}},
        sort=[("id", DESCENDING)],
        projection={"id": 1},
    )
    return int(doc["id"]) if doc and doc.get("id") is not None else 0


def sync_counter(collection_name: str):
    """Make a counter at least as large as the current maximum legacy id."""
    if collection_name not in COUNTER_COLLECTIONS:
        raise ValueError(f"Unknown counter collection: {collection_name}")

    max_id = _max_legacy_id(collection_name)
    get_db().counters.update_one(
        {"_id": collection_name},
        {"$max": {"seq": max_id}},
        upsert=True,
    )


def sync_all_counters():
    for collection_name in COUNTER_COLLECTIONS:
        sync_counter(collection_name)


def next_sequence(collection_name: str) -> int:
    """Atomically allocate the next integer id for a collection."""
    sync_counter(collection_name)
    result = get_db().counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if not result or "seq" not in result:
        raise RuntimeError(f"Unable to allocate id for {collection_name}")
    return int(result["seq"])


def _insert_with_generated_id(collection_name: str, doc: dict) -> int:
    doc["id"] = next_sequence(collection_name)
    _normalize_datetime_fields(doc)
    result = get_db()[collection_name].insert_one(doc)
    if not result.acknowledged:
        raise RuntimeError(f"Insert into {collection_name} was not acknowledged")
    return int(doc["id"])


def init_db():
    """Initialize MongoDB indexes. This never drops data."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
    except ServerSelectionTimeoutError as exc:
        raise RuntimeError(
            f"Cannot connect to MongoDB at {MONGODB_URI}. "
            "Start MongoDB or set MONGODB_URI correctly."
        ) from exc

    db = get_db()
    db.users.create_index([("id", ASCENDING)], unique=True)
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("role", ASCENDING), ("status", ASCENDING)])
    token_repair = db.users.update_many(
        {"token_version": {"$exists": False}}, {"$set": {"token_version": 0}}
    )
    if token_repair.modified_count:
        print(f"Backfilled token_version on {token_repair.modified_count} legacy user(s)")

    db.cases.create_index([("id", ASCENDING)], unique=True)
    db.cases.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.cases.create_index(
        [("author", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db.cases.create_index(
        [("owner_username", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db.cases.create_index([("type", ASCENDING), ("theme", ASCENDING)])
    existing_text_index = db.cases.index_information().get("cases_text_idx")
    existing_weights = (existing_text_index or {}).get("weights", {})
    if existing_text_index and "source_material" not in existing_weights:
        db.cases.drop_index("cases_text_idx")
    db.cases.create_index(
        [("title", TEXT), ("content", TEXT), ("source_material", TEXT), ("keywords", TEXT)],
        name="cases_text_idx",
        default_language="none",
    )

    db.reviews.create_index([("id", ASCENDING)], unique=True)
    db.reviews.create_index([("case_id", ASCENDING), ("review_at", DESCENDING)])
    db.versions.create_index([("id", ASCENDING)], unique=True)
    db.versions.create_index([("case_id", ASCENDING), ("version_number", DESCENDING)])
    db.deployments.create_index([("id", ASCENDING)], unique=True)
    db.deployments.create_index([("case_id", ASCENDING), ("deployed_at", DESCENDING)])

    sync_all_counters()
    repair = backfill_owner_username()
    if repair["fixed"]:
        print(f"Backfilled owner_username on {repair['fixed']} legacy case(s)")
    print(f"MongoDB initialized: {MONGODB_URI}/{MONGODB_DB_NAME}")


def get_user_by_username(username: str) -> dict | None:
    return _serialize_user_doc(get_db().users.find_one({"username": username}))


def create_user(
    username: str,
    password: str,
    role: str = "normal",
    nickname: str = "",
    must_change_password: bool = True,
    status: str = "active",
) -> int:
    _validate_user_role(role)
    _validate_user_status(status)
    if not username:
        raise ValueError("Username cannot be empty")

    doc = {
        "username": username,
        "password": hash_password(password),
        "role": role,
        "nickname": nickname,
        "must_change_password": bool(must_change_password),
        "status": status,
        "token_version": 0,
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        return _insert_with_generated_id("users", doc)
    except DuplicateKeyError as exc:
        raise ValueError(f"Username already exists: {username}") from exc


def get_users_count() -> int:
    return get_db().users.count_documents({})


def serialize_user_public(user: dict | None) -> dict | None:
    serialized = _serialize_user_doc(user)
    if not serialized:
        return None
    serialized.pop("password", None)
    serialized.pop("token_version", None)
    return serialized


def list_users() -> list[dict]:
    cursor = get_db().users.find({}).sort("username", ASCENDING)
    return [serialize_user_public(user) for user in cursor]


def authenticate_user(username: str, password: str) -> dict | None:
    user = get_db().users.find_one({"username": username})
    if not user:
        return None
    if user.get("status") != "active":
        return None
    if not verify_password(password, user.get("password", "")):
        return None
    return _serialize_user_doc(user)


def set_user_password(username: str, new_password: str, must_change_password: bool = True) -> bool:
    result = get_db().users.update_one(
        {"username": username},
        {
            "$set": _normalize_datetime_fields(
                {
                    "password": hash_password(new_password),
                    "must_change_password": bool(must_change_password),
                    "updated_at": _now(),
                }
            ),
            "$inc": {"token_version": 1},
        },
    )
    return result.matched_count > 0 and result.modified_count > 0


def change_user_password(username: str, old_password: str, new_password: str) -> bool:
    user = get_db().users.find_one({"username": username, "status": "active"})
    if not user or not verify_password(old_password, user.get("password", "")):
        return False
    result = get_db().users.update_one(
        {"username": username},
        {
            "$set": _normalize_datetime_fields(
                {
                    "password": hash_password(new_password),
                    "must_change_password": False,
                    "updated_at": _now(),
                }
            ),
            "$inc": {"token_version": 1},
        },
    )
    return result.matched_count > 0 and result.modified_count > 0


def update_user_fields(
    username: str,
    role: str | None = None,
    nickname: str | None = None,
    status: str | None = None,
) -> bool:
    if role is not None:
        _validate_user_role(role)
    if status is not None:
        _validate_user_status(status)

    updates = {}
    if role is not None:
        updates["role"] = role
    if nickname is not None:
        updates["nickname"] = nickname
    if status is not None:
        updates["status"] = status
    if not updates:
        return False
    updates["updated_at"] = _now()

    result = get_db().users.update_one(
        {"username": username}, {"$set": _normalize_datetime_fields(updates)}
    )
    return result.matched_count > 0 and result.modified_count > 0


def rename_user(old_username: str, new_username: str) -> bool:
    if not old_username or not new_username:
        raise ValueError("Username cannot be empty")
    try:
        result = get_db().users.update_one(
            {"username": old_username},
            {"$set": _normalize_datetime_fields({"username": new_username, "updated_at": _now()})},
        )
        return result.matched_count > 0 and result.modified_count > 0
    except DuplicateKeyError as exc:
        raise ValueError(f"Username already exists: {new_username}") from exc


def delete_user(username: str) -> bool:
    result = get_db().users.delete_one({"username": username})
    return result.deleted_count > 0


def clear_users() -> int:
    result = get_db().users.delete_many({})
    sync_counter("users")
    return int(result.deleted_count)


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


def set_case_hidden(case_id: int, hidden: bool) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$set": _normalize_datetime_fields({"is_hidden": bool(hidden), "updated_at": _now()})},
    )
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

    return True


def create_ai_review_version(
    case_id: int,
    reviewer: str,
    ai_review: dict,
    model: str = "",
    raw_answer: str = "",
) -> dict | None:
    db = get_db()
    current = db.cases.find_one({"id": int(case_id), "status": {"$ne": "deleted"}})
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
    version_id = _insert_with_generated_id("versions", version_doc)
    db.cases.update_one(
        {"id": int(case_id)},
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
    return serialize_doc(db.versions.find_one({"id": version_id}))


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

    return {
        "success": result.matched_count > 0,
        "was_in_library": bool(case.get("is_in_library", False)),
        "view_count": int(case.get("view_count") or 0),
        "like_count": int(case.get("like_count") or 0),
        "type": case.get("type"),
        "theme": case.get("theme"),
    }


def _latest_version_id(case_id: int) -> int | None:
    version = get_db().versions.find_one(
        {"case_id": int(case_id)}, sort=[("version_number", DESCENDING)], projection={"id": 1}
    )
    return int(version["id"]) if version and version.get("id") is not None else None


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
    return True


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


def get_case_versions(case_id: int) -> list[dict]:
    cursor = get_db().versions.find({"case_id": int(case_id)}).sort("version_number", DESCENDING)
    return [item for item in (serialize_version(row) for row in cursor) if item is not None]


def get_reviews(case_id: int) -> list[dict]:
    cursor = get_db().reviews.find({"case_id": int(case_id)}).sort("review_at", DESCENDING)
    return [serialize_doc(row) for row in cursor]


def increment_view_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": "approved", "is_hidden": {"$ne": True}},
        {"$inc": {"view_count": 1}},
    )
    return result.matched_count > 0 and result.modified_count > 0


def increment_like_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": "approved", "is_hidden": {"$ne": True}},
        {"$inc": {"like_count": 1}},
    )
    return result.matched_count > 0 and result.modified_count > 0


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
    return correction.modified_count > 0


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
    return stats


if __name__ == "__main__":
    init_db()
