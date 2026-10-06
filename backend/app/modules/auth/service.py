from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    require_strong_password,
    verify_password,
)


class AuthServiceError(ValueError):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class PasswordChangeError(AuthServiceError):
    pass


class RegistrationError(AuthServiceError):
    pass


def register_user(database: Database, username: str, password: str) -> dict:
    try:
        require_strong_password(password)
    except PasswordPolicyError as error:
        raise RegistrationError(str(error), 422) from error

    now = datetime.now(UTC).isoformat()
    user = {
        "id": new_id("u"),
        "username": username,
        "name": username,
        "password_hash": hash_password(password),
        "role": "user",
        "status": "active",
        "must_change_password": False,
        "campus_verified": False,
        "token_version": 0,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        database.users.insert_one(user)
    except DuplicateKeyError as error:
        raise RegistrationError("用户名已存在", 409) from error
    return user


def authenticate(database: Database, username: str, password: str) -> dict | None:
    user = database.users.find_one({"username": username, "status": "active"})
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user


def user_view(user: dict) -> dict:
    view = {key: user[key] for key in ("id", "username", "name", "role")}
    view["mustChangePassword"] = user["must_change_password"]
    view["campusVerified"] = bool(user.get("campus_verified"))
    return view


def change_password(database, user_id: str, current: str, new: str) -> dict:
    user = database.users.find_one({"id": user_id, "status": "active"})
    if not user or not verify_password(current, user["password_hash"]):
        raise PasswordChangeError("当前密码错误", 401)
    _validate_new_password(user, new)
    updated = database.users.find_one_and_update(
        {"_id": user["_id"], "password_hash": user["password_hash"]},
        {"$set": _password_fields(new), "$inc": {"token_version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise PasswordChangeError("密码已在其他位置更新", 409)
    database.sessions.delete_many({"user_id": user_id})
    return updated


def _validate_new_password(user: dict, password: str) -> None:
    try:
        require_strong_password(password, "新密码")
    except PasswordPolicyError as error:
        raise PasswordChangeError(str(error), 422) from error
    if verify_password(password, user["password_hash"]):
        raise PasswordChangeError("新密码不能与当前密码相同", 422)


def _password_fields(password: str) -> dict:
    return {
        "password_hash": hash_password(password),
        "must_change_password": False,
        "updatedAt": datetime.now(UTC).isoformat(),
    }
