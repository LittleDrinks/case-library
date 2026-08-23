from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    require_strong_password,
    verify_password,
)


class PasswordChangeError(ValueError):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def authenticate(database: Database, username: str, password: str) -> dict | None:
    user = database.users.find_one({"username": username, "status": "active"})
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return user


def user_view(user: dict) -> dict:
    view = {key: user[key] for key in ("id", "username", "name", "role")}
    view["mustChangePassword"] = user["must_change_password"]
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
