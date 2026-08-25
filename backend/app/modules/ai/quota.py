from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

CHAT_REQUESTS_PER_MINUTE = 20
DISCOVERIES_PER_MINUTE = 5
USER_CHAT_STREAMS = 2
PROVIDER_CHAT_STREAMS = 32
GLOBAL_CHAT_STREAMS = 64
PROVIDER_DISCOVERIES = 2
GLOBAL_DISCOVERIES = 8
LEASE_SECONDS = 120


class AIQuotaError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AILease:
    database: object
    quota_ids: tuple[str, ...]
    token: str

    def release(self) -> None:
        self.database.ai_usage.delete_many(
            {
                "_id": {"$in": self.quota_ids},
                "token": self.token,
            }
        )


def _now() -> datetime:
    return datetime.now(UTC)


def _provider_id(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/").lower().encode()
    return hashlib.sha256(normalized).hexdigest()[:24]


def _rate_id(scope: str, user_id: str, now: datetime) -> str:
    return f"rate:{scope}:{user_id}:{now:%Y%m%d%H%M}"


def _consume_rate(database, scope: str, user_id: str, limit: int, detail: str) -> None:
    now = _now()
    update = {
        "$inc": {"count": 1},
        "$setOnInsert": {"expiresAt": now + timedelta(minutes=2)},
    }
    row = database.ai_usage.find_one_and_update(
        {"_id": _rate_id(scope, user_id, now)},
        update,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if row["count"] > limit:
        raise AIQuotaError(detail)


def _claim_query(quota_id: str, now: datetime) -> dict:
    return {
        "_id": quota_id,
        "$or": [{"expiresAt": {"$lte": now}}, {"token": {"$exists": False}}],
    }


def _claim_update(token: str, now: datetime) -> dict:
    return {
        "$set": {
            "token": token,
            "expiresAt": now + timedelta(seconds=LEASE_SECONDS),
        }
    }


def _claim(database, quota_id: str, token: str, now: datetime) -> bool:
    try:
        row = database.ai_usage.find_one_and_update(
            _claim_query(quota_id, now), _claim_update(token, now), upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return row is not None
    except DuplicateKeyError:
        return False


def _claim_scope(database, prefix: str, limit: int, token: str, now: datetime):
    for slot in range(limit):
        quota_id = f"concurrent:{prefix}:{slot}"
        if _claim(database, quota_id, token, now):
            return quota_id
    return None


def _acquire(database, scopes: tuple[tuple[str, int], ...], detail: str) -> AILease:
    token, now, claimed = secrets.token_hex(8), _now(), []
    for prefix, limit in scopes:
        quota_id = _claim_scope(database, prefix, limit, token, now)
        if not quota_id:
            AILease(database, tuple(claimed), token).release()
            raise AIQuotaError(detail)
        claimed.append(quota_id)
    return AILease(database, tuple(claimed), token)


def acquire_chat_lease(database, user_id: str, base_url: str) -> AILease:
    _consume_rate(
        database, "chat", user_id, CHAT_REQUESTS_PER_MINUTE, "AI 请求过于频繁"
    )
    provider = _provider_id(base_url)
    scopes = (
        (f"chat:user:{user_id}", USER_CHAT_STREAMS),
        (f"chat:provider:{provider}", PROVIDER_CHAT_STREAMS),
        ("chat:global", GLOBAL_CHAT_STREAMS),
    )
    return _acquire(database, scopes, "AI 服务繁忙，请稍后重试")


def acquire_discovery_lease(database, user_id: str, base_url: str) -> AILease:
    _consume_rate(
        database, "discover", user_id, DISCOVERIES_PER_MINUTE, "模型获取过于频繁"
    )
    provider = _provider_id(base_url)
    scopes = (
        (f"discover:provider:{provider}", PROVIDER_DISCOVERIES),
        ("discover:global", GLOBAL_DISCOVERIES),
    )
    return _acquire(database, scopes, "模型服务繁忙，请稍后重试")
