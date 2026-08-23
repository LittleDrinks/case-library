from __future__ import annotations

import mongomock
import pytest

from app.modules.ai import quota


def database():
    return mongomock.MongoClient()["ai_quota_test"]


def test_provider_bulkhead_is_shared_across_users(monkeypatch) -> None:
    store = database()
    monkeypatch.setattr(quota, "PROVIDER_CHAT_STREAMS", 2)
    leases = [
        quota.acquire_chat_lease(store, f"user-{index}", "https://one.example/v1")
        for index in range(2)
    ]

    with pytest.raises(quota.AIQuotaError, match="AI 服务繁忙"):
        quota.acquire_chat_lease(store, "user-3", "https://one.example/v1")

    other = quota.acquire_chat_lease(store, "user-3", "https://two.example/v1")
    other.release()
    for lease in leases:
        lease.release()


def test_global_bulkhead_spans_different_providers(monkeypatch) -> None:
    store = database()
    monkeypatch.setattr(quota, "GLOBAL_CHAT_STREAMS", 2)
    leases = [
        quota.acquire_chat_lease(store, f"user-{index}", f"https://{index}.example/v1")
        for index in range(2)
    ]

    with pytest.raises(quota.AIQuotaError, match="AI 服务繁忙"):
        quota.acquire_chat_lease(store, "user-3", "https://three.example/v1")

    for lease in leases:
        lease.release()


def test_model_discovery_rate_is_shared_in_database(monkeypatch) -> None:
    store = database()
    monkeypatch.setattr(quota, "DISCOVERIES_PER_MINUTE", 2)

    for _index in range(2):
        quota.acquire_discovery_lease(
            store, "user-1", "https://one.example/v1"
        ).release()

    with pytest.raises(quota.AIQuotaError, match="模型获取过于频繁"):
        quota.acquire_discovery_lease(store, "user-1", "https://one.example/v1")
