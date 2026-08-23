from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pymongo.database import Database

COOKIE_NAME = "case_library_session"


@dataclass(frozen=True, slots=True)
class SessionContext:
    record: dict
    user: dict


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    database: Database, user: dict, ttl_seconds: int
) -> tuple[str, SessionContext]:
    token = secrets.token_urlsafe(32)
    record = {
        "token_hash": _digest(token),
        "csrf_token": secrets.token_urlsafe(32),
        "user_id": user["id"],
        "token_version": user["token_version"],
        "expires_at": datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    }
    database.sessions.insert_one(record)
    return token, SessionContext(record, user)


def find_session(database: Database, token: str | None) -> SessionContext | None:
    if not token:
        return None
    record = database.sessions.find_one(
        {"token_hash": _digest(token), "expires_at": {"$gt": datetime.now(UTC)}}
    )
    if not record:
        return None
    user = database.users.find_one({"id": record["user_id"], "status": "active"})
    if not user or user["token_version"] != record["token_version"]:
        return None
    return SessionContext(record, user)


def delete_session(database: Database, token: str | None) -> None:
    if token:
        database.sessions.delete_one({"token_hash": _digest(token)})
