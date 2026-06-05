#!/usr/bin/env python3
"""MongoDB data access layer for the case library."""

import json
import os
import re
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
}
REVIEW_STATUSES = {"pending", "approved", "rejected", "approve", "reject", "needs_revision"}
USER_ROLES = {"normal", "admin"}
USER_STATUSES = {"active", "no_active"}
COUNTER_COLLECTIONS = ["users", "cases", "reviews", "versions", "deployments"]
VERSIONED_FIELDS = ["title", "type", "theme", "content", "author", "department", "keywords"]
DATETIME_FIELDS = {"created_at", "updated_at", "submitted_at", "review_at", "deployed_at"}
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


def serialize_case(case: dict | None) -> dict | None:
    if case is None:
        return None

    case = serialize_doc(case) or {}
    case["keywords"] = _normalize_keywords(case.get("keywords"))
    case["is_approved"] = bool(case.get("is_approved", False))
    case["is_in_library"] = bool(case.get("is_in_library", False))
    case["is_hidden"] = bool(case.get("is_hidden", False))
    case["view_count"] = int(case.get("view_count") or 0)
    case["like_count"] = int(case.get("like_count") or 0)
    if case.get("status") == "draft":
        case["display_at"] = case.get("updated_at") or case.get("created_at")
    else:
        case["display_at"] = case.get("submitted_at") or case.get("created_at")
    return case


def _now() -> str:
    """Return the current UTC+8 wall-clock time as a plain string."""
    return format_beijing_datetime(datetime.now(UTC))


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

    db.cases.create_index([("id", ASCENDING)], unique=True)
    db.cases.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
    db.cases.create_index(
        [("author", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db.cases.create_index(
        [("owner_username", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)]
    )
    db.cases.create_index([("type", ASCENDING), ("theme", ASCENDING)])
    db.cases.create_index(
        [("title", TEXT), ("content", TEXT), ("keywords", TEXT)],
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
    user = get_db().users.find_one({"username": username})
    serialized = serialize_doc(user)
    if serialized:
        serialized["role"] = _normalize_user_role(serialized.get("role"))
        serialized.setdefault("nickname", "")
        serialized.setdefault("status", "active")
        serialized["must_change_password"] = bool(serialized.get("must_change_password", False))
    return serialized


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
    if not user:
        return None
    serialized = serialize_doc(user) or {}
    serialized.pop("password", None)
    serialized["must_change_password"] = bool(serialized.get("must_change_password", False))
    serialized["role"] = _normalize_user_role(serialized.get("role"))
    serialized.setdefault("nickname", "")
    serialized.setdefault("status", "active")
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
    user["role"] = _normalize_user_role(user.get("role"))
    return serialize_doc(user)


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
            )
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
            )
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
        "status": status,
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
        .limit(max(0, int(limit)))
    )
    return [serialize_case(row) for row in cursor]


def count_cases(
    status: str | None = None,
    author: str | None = None,
    include_hidden: bool = True,
) -> int:
    return get_db().cases.count_documents(
        _case_list_filter(status=status, author=author, include_hidden=include_hidden)
    )


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
        "author",
        "department",
        "status",
        "is_approved",
        "is_in_library",
    ]
    updates = {field: case_data[field] for field in allowed_fields if field in case_data}

    if "keywords" in case_data:
        updates["keywords"] = _normalize_keywords(case_data.get("keywords"))

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
            "content": (updated or {}).get("content", ""),
            "changed_by": updated_by,
            "change_reason": change_reason,
            "created_at": _now(),
        }
        _insert_with_generated_id("versions", version_doc)

    return True


def delete_case(case_id: int) -> dict:
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

    result = db.cases.delete_one({"id": int(case_id)})
    if result.deleted_count > 0:
        db.reviews.delete_many({"case_id": int(case_id)})
        db.versions.delete_many({"case_id": int(case_id)})
        db.deployments.delete_many({"case_id": int(case_id)})

    return {
        "success": result.deleted_count > 0,
        "was_in_library": bool(case.get("is_in_library", False)),
        "view_count": int(case.get("view_count") or 0),
        "like_count": int(case.get("like_count") or 0),
        "type": case.get("type"),
        "theme": case.get("theme"),
    }


def submit_for_review(case_id: int) -> bool:
    db = get_db()
    now = _now()

    result = db.cases.update_one(
        {"id": int(case_id), "status": {"$in": ["draft", "needs_revision"]}},
        {
            "$set": _normalize_datetime_fields(
                {"status": "pending_review", "updated_at": now, "submitted_at": now}
            )
        },
    )
    if result.matched_count == 0 or result.modified_count == 0:
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
                    "updated_at": _now(),
                }
            )
        },
    )
    if result.matched_count == 0:
        return False

    review_doc = {
        "case_id": int(case_id),
        "reviewer": reviewer,
        "comment": comment,
        "status": review_status,
        "review_at": _now(),
    }
    _insert_with_generated_id("reviews", review_doc)
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
    return [serialize_doc(row) for row in cursor]


def get_reviews(case_id: int) -> list[dict]:
    cursor = get_db().reviews.find({"case_id": int(case_id)}).sort("review_at", DESCENDING)
    return [serialize_doc(row) for row in cursor]


def increment_view_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$inc": {"view_count": 1}},
    )
    return result.matched_count > 0 and result.modified_count > 0


def increment_like_count(case_id: int) -> bool:
    result = get_db().cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}},
        {"$inc": {"like_count": 1}},
    )
    return result.matched_count > 0 and result.modified_count > 0


def decrement_like_count(case_id: int) -> bool:
    db = get_db()
    case_exists = (
        db.cases.count_documents({"id": int(case_id), "status": {"$ne": "deleted"}}, limit=1) > 0
    )
    if not case_exists:
        return False

    result = db.cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}, "like_count": {"$gt": 0}},
        {"$inc": {"like_count": -1}},
    )
    if result.modified_count > 0:
        return True

    correction = db.cases.update_one(
        {"id": int(case_id), "status": {"$ne": "deleted"}, "like_count": {"$lt": 0}},
        {"$set": {"like_count": 0}},
    )
    return correction.modified_count > 0


def _status_search_filter(status: str | None) -> dict[str, Any]:
    if not status or status == "all":
        return {"status": {"$nin": ["draft", "deleted"]}}
    if status in ("approved", "approved_all"):
        return {"status": "approved"}
    if status == "rejected":
        return {"status": "needs_revision"}
    if status == "draft":
        return {"status": "__private_draft__"}
    _validate_case_status(status)
    return {"status": status}


def search_cases(
    query: str,
    status: str | None = "approved",
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    if not query or not query.strip():
        return []

    escaped = re.escape(query.strip())
    regex = {"$regex": escaped, "$options": "i"}
    mongo_query: dict[str, Any] = {
        **_status_search_filter(status),
        "is_hidden": {"$ne": True},
        "$or": [{"title": regex}, {"content": regex}, {"keywords": regex}],
    }
    cursor = (
        get_db()
        .cases.find(mongo_query)
        .sort("created_at", DESCENDING)
        .skip(max(0, int(offset)))
        .limit(max(0, int(limit)))
    )
    return [serialize_case(row) for row in cursor]


def filter_cases(
    type_filter: str | None = None,
    theme_filter: str | None = None,
    status_filter: str = "approved",
    keyword_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    query = _status_search_filter(status_filter)
    query["is_hidden"] = {"$ne": True}
    if type_filter:
        query["type"] = type_filter
    if theme_filter:
        query["theme"] = theme_filter
    if keyword_filter:
        regex = {"$regex": re.escape(keyword_filter), "$options": "i"}
        query["$or"] = [{"title": regex}, {"content": regex}, {"keywords": regex}]

    cursor = (
        get_db()
        .cases.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, int(offset)))
        .limit(max(0, int(limit)))
    )
    return [serialize_case(row) for row in cursor]


def get_recommendation_candidates(case_id: int, limit: int = 5) -> list[dict]:
    current_case = get_case(case_id)
    if not current_case:
        return []

    query = {
        "id": {"$ne": int(case_id)},
        "status": "approved",
        "is_hidden": {"$ne": True},
        "$or": [{"type": current_case.get("type")}, {"theme": current_case.get("theme")}],
    }
    cursor = get_db().cases.find(query).limit(max(0, int(limit) * 3))
    cases = [serialize_case(row) for row in cursor]
    cases.sort(key=lambda item: item.get("view_count", 0) + item.get("like_count", 0), reverse=True)
    return cases[:limit]


def get_trending_cases(limit: int = 10) -> list[dict]:
    query = {**_status_search_filter("approved"), "is_hidden": {"$ne": True}}
    cursor = get_db().cases.find(query)
    cases = [serialize_case(row) for row in cursor]
    cases.sort(key=lambda item: item.get("view_count", 0) + item.get("like_count", 0), reverse=True)
    return cases[:limit]


def get_latest_cases(limit: int = 10) -> list[dict]:
    query = {**_status_search_filter("approved"), "is_hidden": {"$ne": True}}
    cursor = get_db().cases.find(query).sort("created_at", DESCENDING).limit(max(0, int(limit)))
    return [serialize_case(row) for row in cursor]


def get_statistics() -> dict:
    db = get_db()
    approved_filter = {"status": "approved"}

    stats: dict[str, Any] = {"total_cases": db.cases.count_documents(approved_filter)}
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
