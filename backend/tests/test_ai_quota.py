from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import mongomock
import pytest

from app.modules.ai import quota


def database():
    return mongomock.MongoClient()["ai_quota_test"]


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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
    assert all(
        row["expiresAt"] >= row_before["expiresAt"]
        for row, row_before in zip(renewed, before)
    )
    lease.release()
    assert store.ai_usage.count_documents({"token": lease.token}) == 0


def test_chat_lease_renews_to_fixed_deadline_and_rejects_expiry_boundary(
    monkeypatch,
) -> None:
    store = database()
    clock = [datetime(2026, 1, 1, 12, 0, tzinfo=UTC)]
    monkeypatch.setattr(quota, "_now", lambda: clock[0])
    lease = quota.acquire_chat_lease(store, "user-1", "https://one.example/v1")
    acquired = list(store.ai_usage.find({"token": lease.token}))
    assert len(acquired) == 3
    assert {row["_id"] for row in acquired} == set(lease.quota_ids)

    renewal_now = clock[0] + timedelta(seconds=5)
    clock[0] = renewal_now
    lease.renew()
    expected = renewal_now + timedelta(seconds=quota.LEASE_SECONDS)
    renewed = list(store.ai_usage.find({"token": lease.token}))
    assert len(renewed) == 3
    assert {row["_id"] for row in renewed} == set(lease.quota_ids)
    assert all(_as_utc(row["expiresAt"]) == expected for row in renewed)

    clock[0] = expected
    before_expiry_attempt = {
        row["_id"]: row["expiresAt"]
        for row in store.ai_usage.find({"token": lease.token})
    }
    with pytest.raises(quota.AIQuotaError, match="^AI 租约已失效$"):
        lease.renew()
    after_expiry_attempt = {
        row["_id"]: row["expiresAt"]
        for row in store.ai_usage.find({"token": lease.token})
    }
    assert after_expiry_attempt == before_expiry_attempt
    lease.release()


def test_reclaimable_normalizes_expiry_and_uses_missing_ttl_fallback() -> None:
    store = database()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    missing = {"_id": "missing", "token": "old"}
    naive_expired = {
        "_id": "naive", "token": "old",
        "expiresAt": (now - timedelta(seconds=1)).replace(tzinfo=None),
    }
    offset_expired = {
        "_id": "offset", "token": "old",
        "expiresAt": (now - timedelta(hours=1)).astimezone(timezone(timedelta(hours=2))),
    }

    assert quota._reclaimable(store, missing, now)
    assert quota._reclaimable(store, naive_expired, now)
    assert quota._reclaimable(store, offset_expired, now)


def test_claim_reclaims_expired_rows_but_fences_future_and_active_owners() -> None:
    store = database()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    store.ai_usage.insert_many([
        {"_id": "future", "token": "old", "expiresAt": now + timedelta(seconds=1)},
        {"_id": "exact", "token": "old", "expiresAt": now},
        {
            "_id": "owned", "token": "old", "runId": "run-1",
            "expiresAt": now - timedelta(seconds=1),
        },
    ])
    store.agent_runs.insert_one({
        "id": "run-1", "status": "active", "ownerExpiresAt": now + timedelta(seconds=10),
    })

    future_before = store.ai_usage.find_one({"_id": "future"}, {"_id": 0})
    assert not quota._claim(store, "future", "new-future", now)
    assert store.ai_usage.find_one({"_id": "future"}, {"_id": 0}) == future_before

    exact_before = store.ai_usage.find_one({"_id": "exact"}, {"_id": 0})
    assert quota._claim(store, "exact", "new-exact", now)
    exact_after = store.ai_usage.find_one({"_id": "exact"}, {"_id": 0})
    assert exact_after["token"] == "new-exact"
    assert _as_utc(exact_after["expiresAt"]) == now + timedelta(seconds=quota.LEASE_SECONDS)
    assert "runId" not in exact_after
    assert exact_before["token"] == "old"

    owned_before = store.ai_usage.find_one({"_id": "owned"}, {"_id": 0})
    assert not quota._claim(store, "owned", "new-owned", now)
    assert store.ai_usage.find_one({"_id": "owned"}, {"_id": 0}) == owned_before

    store.agent_runs.update_one(
        {"id": "run-1"}, {"$set": {"ownerExpiresAt": now - timedelta(seconds=1)}}
    )
    assert quota._claim(store, "owned", "new-owned", now)
    owned_after = store.ai_usage.find_one({"_id": "owned"}, {"_id": 0})
    assert owned_after["token"] == "new-owned"
    assert _as_utc(owned_after["expiresAt"]) == now + timedelta(seconds=quota.LEASE_SECONDS)
    assert "runId" not in owned_after
def test_expired_lease_is_not_reclaimed_until_run_owner_expires() -> None:
    store = database()
    now = datetime.now(UTC)
    quota_id = "concurrent:chat:provider:test:0"
    store.ai_usage.insert_one({
        "_id": quota_id, "token": "old", "runId": "run-1",
        "expiresAt": now - timedelta(seconds=1),
    })
    store.agent_runs.insert_one({
        "id": "run-1", "status": "active", "ownerId": "worker-a",
        "ownerExpiresAt": now + timedelta(seconds=10),
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
