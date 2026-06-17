"""Public read cache seam.

The current public read cache is intentionally in-process and conservative.
This module centralizes the invalidation boundary so repository write paths do
not know which public read surfaces are cached.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any


class JsonReadCache:
    """Small JSON-copying cache for public read payloads."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def get(self, key: str) -> Any | None:
        now = datetime.now(UTC)
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires_at = entry.get("expires_at")
            if not isinstance(expires_at, datetime) or expires_at <= now:
                self._store.pop(key, None)
                return None
            return json.loads(json.dumps(entry.get("data")))

    def set(self, key: str, data: Any, ttl_seconds: int) -> Any:
        with self._lock:
            cached = json.loads(json.dumps(data))
            self._store[key] = {
                "data": cached,
                "expires_at": datetime.now(UTC) + timedelta(seconds=max(0, int(ttl_seconds))),
            }
            return json.loads(json.dumps(cached))

    def invalidate(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._store.clear()
                return
            for key in list(self._store):
                if key.startswith(prefix):
                    self._store.pop(key, None)


public_read_cache = JsonReadCache()


def invalidate_public_read_caches(reason: str = "") -> None:
    """Invalidate every public read cache affected by public-case writes."""

    public_read_cache.invalidate()


__all__ = ["JsonReadCache", "invalidate_public_read_caches", "public_read_cache"]
