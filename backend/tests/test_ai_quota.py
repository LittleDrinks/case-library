from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
        quota.acquire_discovery_lease(store, "user-1", "https://one.example/v1").release()
    with pytest.raises(quota.AIQuotaError, match="模型获取过于频繁"):
        quota.acquire_discovery_lease(store, "user-1", "https://one.example/v1")


def test_chat_lease_binds_renews_and_releases_exact_slots() -> None:
    store = database()
    lease = quota.acquire_chat_lease(store, "user-1", "https://one.example/v1")
    before = list(store.ai_usage.find({"token": lease.token}))
    lease.bind_run("run-1")
    bound = list(store.ai_usage.find({"token": lease.token}))
    assert all(row["runId"] == "run-1" for row in bound)
    lease.renew()
    renewed = list(store.ai_usage.find({"token": lease.token}))
    assert all(row["expiresAt"] >= row_before["expiresAt"] for row, row_before in zip(renewed, before))
    lease.release()
    assert store.ai_usage.count_documents({"token": lease.token}) == 0


def test_expired_lease_is_not_reclaimed_until_run_owner_expires(monkeypatch) -> None:
    store = database()
    now = datetime.now(UTC)
    quota_id = "concurrent:chat:provider:test:0"
    store.ai_usage.insert_one({
        "_id": quota_id, "token": "old", "runId": "run-1",
        "expiresAt": now - timedelta(seconds=1),
    })
    store.agent_runs.insert_one({
        "id": "run-1", "status": "active",
        "ownerId": "worker-a", "ownerExpiresAt": now + timedelta(seconds=10),
    })
    assert not quota._claim(store, quota_id, "new", now)
    store.agent_runs.update_one(
        {"id": "run-1"}, {"$set": {"ownerExpiresAt": now - timedelta(seconds=1)}}
    )
    assert quota._claim(store, quota_id, "new", now)


def test_missing_ttl_rows_stay_fenced_by_an_active_run(monkeypatch) -> None:
    store = database()
    monkeypatch.setattr(quota, "USER_CHAT_STREAMS", 1)
    monkeypatch.setattr(quota, "PROVIDER_CHAT_STREAMS", 1)
    monkeypatch.setattr(quota, "GLOBAL_CHAT_STREAMS", 1)
    lease = quota.acquire_chat_lease(store, "user-1", "https://one.example/v1")
    now = datetime.now(UTC)
    store.agent_runs.insert_one({
        "id": "run-1", "status": "active", "ownerId": "worker-a",
        "ownerExpiresAt": now + timedelta(seconds=10),
        "quotaIds": list(lease.quota_ids),
    })
    lease.bind_run("run-1")
    store.ai_usage.delete_many({"_id": {"$in": lease.quota_ids}})

    with pytest.raises(quota.AIQuotaError, match="AI 服务繁忙"):
        quota.acquire_chat_lease(store, "user-1", "https://one.example/v1")
