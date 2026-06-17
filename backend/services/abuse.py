"""Anti-abuse seams for public interaction writes."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any


class PublicInteractionRateLimitExceededError(Exception):
    """Raised when a public interaction exceeds the configured policy."""


@dataclass(frozen=True)
class PublicInteractionIdentity:
    key: str
    source: str = "anonymous"


def _hash_identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def public_interaction_identity(
    request: Any = None,
    *,
    headers: dict[str, str] | None = None,
    client_host: str | None = None,
) -> PublicInteractionIdentity:
    """Build a non-secret stable key for public like/view style writes."""

    request_headers = headers
    if request is not None and request_headers is None:
        request_headers = dict(getattr(request, "headers", {}) or {})
    request_headers = {str(k).lower(): str(v) for k, v in (request_headers or {}).items()}

    forwarded_for = request_headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    real_ip = request_headers.get("x-real-ip", "").strip()
    host = forwarded_for or real_ip or client_host or ""
    if not host and request is not None and getattr(request, "client", None):
        host = getattr(request.client, "host", "") or ""

    user_agent = request_headers.get("user-agent", "").strip()
    raw = "|".join(part for part in (host, user_agent) if part)
    if not raw:
        return PublicInteractionIdentity(key="anonymous", source="anonymous")
    return PublicInteractionIdentity(key=_hash_identity(raw), source="request")


class FixedWindowRateLimiter:
    """In-process fixed-window limiter; disabled when max_events <= 0."""

    def __init__(self, max_events: int = 0, window_seconds: int = 60) -> None:
        self.max_events = int(max_events)
        self.window_seconds = max(1, int(window_seconds))
        self._events: dict[tuple[str, str], list[float]] = {}
        self._lock = RLock()

    def allow(self, action: str, identity: PublicInteractionIdentity | None = None) -> bool:
        if self.max_events <= 0:
            return True
        now = time.monotonic()
        identity_key = (identity or PublicInteractionIdentity("anonymous")).key
        bucket_key = (action, identity_key)
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = [event_at for event_at in self._events.get(bucket_key, []) if event_at > cutoff]
            if len(bucket) >= self.max_events:
                self._events[bucket_key] = bucket
                return False
            bucket.append(now)
            self._events[bucket_key] = bucket
            return True


public_interaction_rate_limiter = FixedWindowRateLimiter()


def ensure_public_interaction_allowed(
    action: str,
    identity: PublicInteractionIdentity | None = None,
) -> None:
    if not public_interaction_rate_limiter.allow(action, identity):
        raise PublicInteractionRateLimitExceededError("public interaction rate limit exceeded")


__all__ = [
    "FixedWindowRateLimiter",
    "PublicInteractionIdentity",
    "PublicInteractionRateLimitExceededError",
    "ensure_public_interaction_allowed",
    "public_interaction_identity",
    "public_interaction_rate_limiter",
]
