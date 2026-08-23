from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.modules.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    require_strong_password,
)


class AdminBootstrapError(ValueError):
    pass


def _required(value: str, label: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise AdminBootstrapError(f"{label}不能为空")
    if len(normalized) > maximum:
        raise AdminBootstrapError(f"{label}不能超过 {maximum} 个字符")
    return normalized


def _admin_record(username: str, name: str, password: str) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": f"u-{secrets.token_hex(12)}",
        "username": username,
        "name": name,
        "password_hash": hash_password(password),
        "role": "admin",
        "status": "active",
        "must_change_password": False,
        "token_version": 0,
        "createdAt": now,
        "updatedAt": now,
    }


def bootstrap_admin(
    database: Database, username: str, name: str, password: str
) -> dict:
    username = _required(username, "用户名", 80)
    name = _required(name, "姓名", 120)
    try:
        require_strong_password(password)
    except PasswordPolicyError as error:
        raise AdminBootstrapError(str(error)) from error
    user = _admin_record(username, name, password)
    try:
        database.users.insert_one(user)
    except DuplicateKeyError as error:
        raise AdminBootstrapError(f"用户名已存在：{username}") from error
    return user
