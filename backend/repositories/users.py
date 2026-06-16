"""User repository helpers."""

from __future__ import annotations

import bcrypt
from db.connection import get_db
from db.counters import _insert_with_generated_id, sync_counter
from db.datetime import _normalize_datetime_fields
from db.validators import (
    _normalize_token_version,
    _normalize_user_role,
    _now,
    _validate_user_role,
    _validate_user_status,
)
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from serializers import serialize_doc


def _serialize_user_doc(user: dict | None) -> dict | None:
    serialized = serialize_doc(user)
    if serialized:
        serialized["role"] = _normalize_user_role(serialized.get("role"))
        serialized.setdefault("nickname", "")
        serialized.setdefault("status", "active")
        serialized["must_change_password"] = bool(serialized.get("must_change_password", False))
        serialized["token_version"] = _normalize_token_version(serialized.get("token_version"))
    return serialized

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
