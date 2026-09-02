from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
import pytest
from pymongo import MongoClient

from app.modules.ai import quota
from app.modules.agent.repository import AgentRepository


BASE_URL = os.environ.get("AGENT_CASE_LIBRARY_E2E_URL")
LOSER_BASE_URL = os.environ.get("AGENT_CASE_LIBRARY_E2E_LOSER_URL")
MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
PROFILE_APPS = ("agent-e2e-app", "agent-e2e-loser")
AGENT_COLLECTIONS = ("agent_messages", "agent_runs", "agent_thread_events")
E2E_PROVIDER = "http://ai-provider:8080/v1"
E2E_API_KEY = "e2e-api-key"
E2E_ANSWER = "隔离模型回答：已依据当前可见资源完成分析。"
pytestmark = pytest.mark.e2e(
    "AGENT_CASE_LIBRARY_E2E_URL",
    "AGENT_CASE_LIBRARY_E2E_LOSER_URL",
    "AUTH_QUERY_MONGODB_URI",
)


def _login(
    username: str = "user", password: str = "user123", base_url: str = BASE_URL
) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=base_url)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    csrf = response.json()["csrfToken"]
    _configure_provider(client, csrf)
    return client, csrf


def _configure_provider(client: httpx.Client, csrf: str) -> None:
    response = client.put(
        "/api/ai/settings", headers={"X-CSRF-Token": csrf},
        json={"mode": "custom", "baseUrl": E2E_PROVIDER,
              "apiKey": E2E_API_KEY, "model": "e2e-model-a"},
    )
    assert response.status_code == 200


def _create_case(client: httpx.Client, csrf: str) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": csrf},
        json={"title": f"Agent Mongo {uuid.uuid4().hex}"},
    )
    assert response.status_code == 200
    return response.json()


def _thread(client: httpx.Client, case_id: str) -> dict:
    response = client.get(f"/api/cases/{case_id}/agent/thread")
    assert response.status_code == 200
    return response.json()


def _body(message_id: str, text: str) -> dict:
    return {
        "id": f"chat-{message_id}",
        "trigger": "submit-message",
        "messages": [{
            "id": message_id,
            "role": "user",
            "parts": [{"type": "text", "text": text}],
        }],
    }


def _send(
    client: httpx.Client, csrf: str, case_id: str, text: str, message_id: str,
    content=None, thread_id=None,
):
    thread_id = thread_id or _thread(client, case_id)["id"]
    request = {"headers": {"X-CSRF-Token": csrf}, "timeout": 15}
    request["content" if content else "json"] = content or _body(message_id, text)
    return client.post(
        f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
        **request,
    )


def _events(database, thread_id: str) -> list[dict]:
    return list(
        database.agent_thread_events.find({"threadId": thread_id}, {"_id": 0})
        .sort("eventSeq", 1)
    )


def _await_active(database, thread_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": "active"}, {"_id": 0}
        )
        if run:
            return run
        Event().wait(0.02)
    pytest.fail("real MongoDB run did not become active")


def _await_status(database, run_id: str, status: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = database.agent_runs.find_one(
            {"id": run_id, "status": status}, {"_id": 0}
        )
        if run:
            return run
        Event().wait(0.02)
    actual = database.agent_runs.find_one({"id": run_id}, {"_id": 0})
    pytest.fail(f"real MongoDB run did not become {status}: {actual}")


def _assert_terminal(snapshot: dict, events: list[dict]) -> None:
    assert snapshot["eventSeq"] == 4
    assert [message["messageSeq"] for message in snapshot["messages"]] == [1, 2]
    assert [message["role"] for message in snapshot["messages"]] == ["user", "assistant"]
    assert snapshot["messages"][-1]["parts"][0]["text"] == E2E_ANSWER
    assert snapshot["activeRun"] is None
    assert snapshot["latestRun"]["status"] == "completed"
    assert [event["eventSeq"] for event in events] == [1, 2, 3, 4]
    assert [event["type"] for event in events] == [
        "message.created", "run.started", "message.created", "run.completed"
    ]
    assert all(event["runId"] == snapshot["latestRun"]["id"] for event in events)


def _assert_no_late_event(database, thread_id: str, run_id: str, before: int) -> None:
    assert not AgentRepository(database).append_event(
        thread_id, "message.created", run_id, {"messageId": "late-real-event"}
    )
    assert len(_events(database, thread_id)) == before
    assert database.agent_threads.find_one({"id": thread_id})["eventSeq"] == before


def _assert_thread_counts(database, thread_id: str) -> None:
    assert database.agent_runs.count_documents({"threadId": thread_id}) == 1
    assert database.agent_messages.count_documents({"threadId": thread_id}) == 2
    assert database.agent_thread_events.count_documents({"threadId": thread_id}) == 4
    assert database.agent_runs.count_documents({"threadId": thread_id, "status": "active"}) == 0
    assert database.agent_threads.find_one({"id": thread_id})["activeRunId"] is None


def _close(*clients, mongo) -> None:
    for client in clients:
        client.close()
    mongo.close()


def _collection_counts(database, thread_id: str) -> tuple[int, int, int]:
    return (
        database.agent_runs.count_documents({"threadId": thread_id}),
        database.agent_messages.count_documents({"threadId": thread_id}),
        database.agent_thread_events.count_documents({"threadId": thread_id}),
    )


def _hold_thread_write(database, thread_id: str):
    session = database.client.start_session()
    session.start_transaction()
    database.agent_threads.update_one(
        {"id": thread_id}, {"$set": {"probe": uuid.uuid4().hex}}, session=session
    )
    return session


def _start_profile(database) -> None:
    database.command("profile", 0, filter={})
    database.command(
        "profile",
        2,
        filter={
            "ns": {"$regex": rf"^{database.name}[.]agent_"},
            "appName": {"$in": PROFILE_APPS},
        },
    )


def _restore_profile(database) -> None:
    database.command(
        "profile", 0, filter={"ns": {"$regex": rf"^{database.name}[.]agent_"}}
    )


def _reservation_rows(database, thread_id: str, app_name: str) -> list[dict]:
    query = {
        "ns": f"{database.name}.agent_threads",
        "appName": app_name,
        "command.findAndModify": "agent_threads",
        "command.query.id": thread_id,
        "command.query.activeRunId": None,
        "command.query.eventSeq": {"$exists": True},
        "command.query.nextMessageSeq": {"$exists": True},
    }
    return list(database.system.profile.find(query, {"_id": 0}).sort("ts", 1))


def _snapshot_rows(database, thread_id: str) -> list[dict]:
    query = {
        "ns": f"{database.name}.agent_runs",
        "appName": "agent-e2e-loser",
        "command.find": "agent_runs",
        "command.filter.threadId": thread_id,
    }
    return list(database.system.profile.find(query, {"_id": 0}).sort("ts", 1))


def _wait_for_profile(database, query: dict, check, message: str):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        rows = list(database.system.profile.find(query, {"_id": 0}).sort("ts", 1))
        if check(rows):
            return rows
        Event().wait(0.02)
    pytest.fail(message)


def _wait_for_winner_conflict(database, thread_id: str) -> None:
    query = {
        "ns": f"{database.name}.agent_threads", "appName": "agent-e2e-app",
        "command.findAndModify": "agent_threads", "command.query.id": thread_id,
        "errCode": 112,
    }
    _wait_for_profile(database, query, bool, "winner reservation was not held")


def _wait_for_loser_snapshot(database, thread_id: str) -> None:
    query = {
        "ns": f"{database.name}.agent_runs", "appName": "agent-e2e-loser",
        "command.find": "agent_runs", "command.filter.threadId": thread_id,
    }
    _wait_for_profile(database, query, bool, "loser transaction snapshot was not observed")


def _submit_concurrent_posts(pool, winner, winner_csrf, loser, loser_csrf, case, thread_id, database):
    winner_future = pool.submit(
        _send, winner, winner_csrf, case["id"], "并发完成优先", "real-winner", thread_id=thread_id
    )
    _wait_for_winner_conflict(database, thread_id)
    loser_future = pool.submit(
        _send, loser, loser_csrf, case["id"], "并发完成优先", "real-loser", thread_id=thread_id
    )
    _wait_for_loser_snapshot(database, thread_id)
    return [winner_future, loser_future]


def _change_label(change, thread_id: str):
    document = change.get("fullDocument") or {}
    if document.get("threadId") != thread_id:
        return None
    collection = change["ns"]["coll"]
    if collection == "agent_messages" and document.get("role") == "assistant":
        return "assistant-message", document["runId"]
    if collection == "agent_runs" and document.get("status") == "completed":
        return "terminal-run", document["id"]
    if collection == "agent_thread_events" and document.get("type") == "run.completed":
        return "terminal-event", document["runId"]
    return None


def _change_observation(change, thread_id: str) -> dict | None:
    label = _change_label(change, thread_id)
    if not label:
        return None
    return {
        "label": label[0],
        "runId": label[1],
        "wallTime": change.get("wallTime"),
        "clusterTime": change.get("clusterTime"),
        "transactionId": (change.get("lsid"), change.get("txnNumber")),
    }


def _terminal_changes(stream, thread_id: str) -> list[dict]:
    changes = []
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and len(changes) < 3:
        change = stream.try_next()
        observation = _change_observation(change, thread_id) if change else None
        if observation and observation["label"] not in [item["label"] for item in changes]:
            changes.append(observation)
        if not change:
            Event().wait(0.02)
    if len(changes) != 3:
        pytest.fail(f"Change Stream did not expose terminal order: {changes}")
    return changes


def _assert_change_order(changes: list[dict]) -> None:
    assert [item["label"] for item in changes] == [
        "assistant-message", "terminal-run", "terminal-event"
    ]
    assert len({item["runId"] for item in changes}) == 1
    assert all(item["wallTime"] for item in changes)
    assert all(item["transactionId"][0] for item in changes)
    assert all(item["transactionId"][1] is not None for item in changes)
    assert all(item["transactionId"] == changes[0]["transactionId"] for item in changes)


def _assert_retry_after_terminal(database, thread_id: str, changes: list[dict]) -> None:
    rows = _reservation_rows(database, thread_id, "agent-e2e-loser")
    assert len(rows) == 2
    assert rows[0]["errCode"] == 112
    assert rows[1].get("errCode") is None
    assert rows[0]["command"]["lsid"] == rows[1]["command"]["lsid"]
    assert rows[0]["command"]["txnNumber"] != rows[1]["command"]["txnNumber"]
    assert rows[1]["ts"] >= changes[-1]["wallTime"]


def _run_posts(
    pool, winner, winner_csrf, loser, loser_csrf, case, thread_id, stream, database, holder
):
    futures = _submit_concurrent_posts(
        pool, winner, winner_csrf, loser, loser_csrf, case, thread_id, database
    )
    assert not any(future.done() for future in futures)
    holder.abort_transaction()
    changes = _terminal_changes(stream, thread_id)
    return changes, [future.result(timeout=15) for future in futures]


def _run_gated_overlap(winner, winner_csrf, loser, loser_csrf, case, database, thread_id):
    pipeline = [{"$match": {"ns.coll": {"$in": AGENT_COLLECTIONS}}}]
    with database.watch(pipeline, full_document="updateLookup", max_await_time_ms=100) as stream:
        holder = _hold_thread_write(database, thread_id)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                return _run_posts(
                    pool, winner, winner_csrf, loser, loser_csrf, case,
                    thread_id, stream, database, holder,
                )
        finally:
            if holder.in_transaction:
                holder.abort_transaction()
            holder.end_session()


def _assert_http_results(responses) -> None:
    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json() == {"detail": "当前对话已有运行任务"}


def _assert_completion_first_state(winner, case, database, thread_id, changes) -> None:
    snapshot = _thread(winner, case["id"])
    _assert_terminal(snapshot, _events(database, thread_id))
    _assert_thread_counts(database, thread_id)
    _assert_change_order(changes)
    _assert_retry_after_terminal(database, thread_id, changes)


def _send_while_observing(client, csrf, case, thread_id, stream):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            _send, client, csrf, case["id"], "Change Stream 顺序", "real-order",
            thread_id=thread_id,
        )
        changes = _terminal_changes(stream, thread_id)
        return future.result(timeout=15), changes


def test_agent_http_real_replica_set_rejects_completion_first_transaction_retry():
    winner, winner_csrf = _login()
    loser, loser_csrf = _login(base_url=LOSER_BASE_URL)
    mongo = MongoClient(MONGO_URI)
    database = mongo.get_default_database()
    try:
        case = _create_case(winner, winner_csrf)
        thread_id = _thread(winner, case["id"])["id"]
        _start_profile(database)
        changes, responses = _run_gated_overlap(
            winner, winner_csrf, loser, loser_csrf, case, database, thread_id
        )
        _assert_http_results(responses)
        _assert_completion_first_state(winner, case, database, thread_id, changes)
    finally:
        _restore_profile(database)
        _close(winner, loser, mongo=mongo)


def test_agent_http_change_stream_proves_terminal_write_order():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(client, csrf)
        thread_id = _thread(client, case["id"])["id"]
        database = mongo.get_default_database()
        pipeline = [{"$match": {"ns.coll": {"$in": [
            "agent_messages", "agent_runs", "agent_thread_events"
        ]}}}]
        with database.watch(pipeline, full_document="updateLookup", max_await_time_ms=100) as stream:
            response, changes = _send_while_observing(
                client, csrf, case, thread_id, stream
            )
        assert response.status_code == 200
        _assert_change_order(changes)
    finally:
        _close(client, mongo=mongo)


def test_agent_http_uses_real_replica_set_for_atomic_terminal_state_and_idempotency():
    client, csrf = _login()
    duplicate, duplicate_csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(client, csrf)
        thread_id = _thread(client, case["id"])["id"]
        first = _send(client, csrf, case["id"], "并发慢请求", "real-first")
        assert first.status_code == 200
        database = mongo.get_default_database()
        snapshot = _thread(client, case["id"])
        events = _events(database, thread_id)
        _assert_terminal(snapshot, events)
        run_id, before = snapshot["latestRun"]["id"], len(events)
        retry = _send(duplicate, duplicate_csrf, case["id"], "并发慢请求", "real-first")
        assert retry.status_code == 409
        _assert_no_late_event(database, thread_id, run_id, before)
    finally:
        _close(client, duplicate, mongo=mongo)


def _overlap(holder, holder_csrf, challenger, challenger_csrf, case, database):
    thread_id = _thread(holder, case["id"])["id"]
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            _send, holder, holder_csrf, case["id"], "并发慢请求", "real-holder"
        )
        run = _await_active(database, thread_id)
        conflict = _send(
            challenger, challenger_csrf, case["id"], "并发冲突请求", "real-challenger"
        )
        response = future.result(timeout=15)
    return thread_id, run, conflict, response


def test_agent_http_real_replica_set_rejects_overlap_before_holder_completes():
    holder, holder_csrf = _login()
    challenger, challenger_csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(holder, holder_csrf)
        database = mongo.get_default_database()
        thread_id, run, conflict, response = _overlap(
            holder, holder_csrf, challenger, challenger_csrf, case, database
        )
        assert conflict.status_code == 409
        assert response.status_code == 200
        _assert_thread_counts(database, thread_id)
        assert run["status"] == "active"
    finally:
        _close(holder, challenger, mongo=mongo)


def test_agent_http_cross_user_post_does_not_create_thread_records():
    victim, victim_csrf = _login()
    attacker, attacker_csrf = _login("admin", "admin123")
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(victim, victim_csrf)
        thread_id = _thread(victim, case["id"])["id"]
        database = mongo.get_default_database()
        before = _collection_counts(database, thread_id)
        response = attacker.post(
            f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream",
            headers={"X-CSRF-Token": attacker_csrf},
            json=_body("cross-user", "越权请求"),
        )
        assert response.status_code == 403
        assert _collection_counts(database, thread_id) == before == (0, 0, 0)
        assert _thread(victim, case["id"])["eventSeq"] == 0
    finally:
        _close(victim, attacker, mongo=mongo)


def test_agent_http_real_mongo_upstream_failure_is_terminal_and_fenced():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(client, csrf)
        database = mongo.get_default_database()
        thread_id = _thread(client, case["id"])["id"]
        response = _send(
            client, csrf, case["id"], "上游中断测试", "failure-real", thread_id=thread_id
        )
        assert response.status_code == 200
        _assert_failed_terminal(client, database, case["id"], thread_id)
    finally:
        _close(client, mongo=mongo)


def test_agent_http_client_disconnect_cancels_run_and_releases_lease():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(client, csrf)
        database = mongo.get_default_database()
        thread_id = _thread(client, case["id"])["id"]
        path = f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream"
        with client.stream(
            "POST", path, headers={"X-CSRF-Token": csrf},
            json=_body("cancel-real", "取消测试"), timeout=15,
        ) as response:
            assert response.status_code == 200
            run = _await_active(database, thread_id)
            next(response.iter_bytes())
        _assert_cancelled(database, thread_id, run["id"])
    finally:
        _close(client, mongo=mongo)


def test_agent_http_renews_quota_while_long_provider_run_is_active():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(client, csrf)
        database = mongo.get_default_database()
        thread_id = _thread(client, case["id"])["id"]
        path = f"/api/cases/{case['id']}/agent/thread/{thread_id}/stream"
        with client.stream(
            "POST", path, headers={"X-CSRF-Token": csrf},
            json=_body("renew-real", "慢速测试"), timeout=15,
        ) as response:
            assert response.status_code == 200
            run = _await_active(database, thread_id)
            _assert_leases_renewed(database, run["id"])
            response.read()
        _assert_completed_and_released(database, run["id"])
    finally:
        _close(client, mongo=mongo)


def _ttl_lease(database, monkeypatch):
    for name in ("USER_CHAT_STREAMS", "PROVIDER_CHAT_STREAMS", "GLOBAL_CHAT_STREAMS"):
        monkeypatch.setattr(quota, name, 1)
    return quota.acquire_chat_lease(database, "ttl-owner", E2E_PROVIDER)


def _insert_ttl_owner(database, lease):
    run_id = f"ttl-run-{uuid.uuid4().hex}"
    now = datetime.now(UTC)
    database.agent_runs.insert_one({
        "id": run_id, "status": "active", "ownerId": "worker-a",
        "ownerExpiresAt": now + timedelta(seconds=30),
        "quotaIds": list(lease.quota_ids),
    })
    lease.bind_run(run_id)
    return run_id, now


def _prove_ttl_fence(database, lease, run_id, now):
    database.client.admin.command("setParameter", 1, ttlMonitorSleepSecs=1)
    before = _ttl_deleted(database)
    database.ai_usage.update_many(
        {"_id": {"$in": lease.quota_ids}},
        {"$set": {"expiresAt": now - timedelta(seconds=1)}},
    )
    _await_ttl_deletion(database, lease.quota_ids, before)
    with pytest.raises(quota.AIQuotaError, match="AI 服务繁忙"):
        quota.acquire_chat_lease(database, "ttl-owner", E2E_PROVIDER)
    database.agent_runs.update_one(
        {"id": run_id}, {"$set": {"ownerExpiresAt": now - timedelta(seconds=1)}}
    )
    reclaimed = quota.acquire_chat_lease(database, "ttl-owner", E2E_PROVIDER)
    assert set(reclaimed.quota_ids) == set(lease.quota_ids)
    return reclaimed


def test_real_mongo_ttl_deletion_keeps_active_run_quota_fenced(monkeypatch):
    mongo = MongoClient(MONGO_URI)
    database = mongo.get_default_database()
    run_id = None
    lease = reclaimed = None
    try:
        lease = _ttl_lease(database, monkeypatch)
        run_id, now = _insert_ttl_owner(database, lease)
        reclaimed = _prove_ttl_fence(database, lease, run_id, now)
    finally:
        if lease:
            lease.release()
        if reclaimed:
            reclaimed.release()
        if run_id:
            database.agent_runs.delete_one({"id": run_id})
        mongo.close()


def _takeover_owner(database, run: dict) -> None:
    changed = database.agent_runs.update_one(
        {"id": run["id"], "status": "active", "ownerId": run["ownerId"]},
        {"$set": {
            "ownerId": "worker-takeover",
            "ownerExpiresAt": datetime.now(UTC) + timedelta(seconds=10),
        }},
    )
    assert changed.matched_count == 1


def _run_after_owner_takeover(client, csrf, case, database, thread_id):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            _send, client, csrf, case["id"], "取消测试", "lost-owner", thread_id=thread_id
        )
        run = _await_active(database, thread_id)
        leases = _await_run_leases(database, run["id"])
        assert {row["_id"] for row in leases} == set(run["quotaIds"])
        _takeover_owner(database, run)
        try:
            future.result(timeout=15)
        except httpx.RemoteProtocolError as error:
            return error, run
    pytest.fail("the live Agent stream was not cancelled after ownership loss")


def test_agent_http_heartbeat_loss_stops_the_live_worker():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(client, csrf)
        database = mongo.get_default_database()
        thread_id = _thread(client, case["id"])["id"]
        transport, run = _run_after_owner_takeover(client, csrf, case, database, thread_id)
        assert isinstance(transport, httpx.RemoteProtocolError)
        _assert_lost_worker_state(database, thread_id, run["id"])
        _await_released(database, run["id"])
    finally:
        _close(client, mongo=mongo)


def _assert_cancelled(database, thread_id: str, run_id: str) -> None:
    terminal = _await_status(database, run_id, "cancelled")
    assert terminal["error"] == "运行已取消"
    assert _events(database, thread_id)[-1]["type"] == "run.cancelled"
    _await_released(database, run_id)


def _assert_failed_terminal(client, database, case_id: str, thread_id: str) -> None:
    snapshot = _thread(client, case_id)
    events = _events(database, thread_id)
    run_id = snapshot["latestRun"]["id"]
    assert snapshot == _thread(client, case_id)
    assert snapshot["activeRun"] is None
    assert snapshot["latestRun"]["status"] == "failed"
    assert snapshot["latestRun"]["error"] == "AI 服务暂不可用"
    assert [event["eventSeq"] for event in events] == [1, 2, 3]
    assert [event["type"] for event in events] == [
        "message.created", "run.started", "run.failed"
    ]
    assert _collection_counts(database, thread_id) == (1, 1, 3)
    assert not AgentRepository(database).fail_run(run_id)
    _assert_no_late_event(database, thread_id, run_id, len(events))
    _await_released(database, run_id)


def _all_leases_renewed(run, owner_expiry, current, initial) -> bool:
    return (
        run and run["ownerExpiresAt"] > owner_expiry
        and set(current) == set(initial)
        and all(current[key] > value for key, value in initial.items())
    )


def _lease_rows(database, run_id: str) -> list[dict]:
    return list(database.ai_usage.find(
        {"runId": run_id}, {"_id": 1, "token": 1, "expiresAt": 1}
    ))


def _assert_leases_renewed(database, run_id: str) -> None:
    run = database.agent_runs.find_one({"id": run_id, "status": "active"})
    leases = _lease_rows(database, run_id)
    assert run and run["ownerId"] and run["ownerExpiresAt"]
    assert len(leases) == 3
    assert set(row["_id"] for row in leases) == set(run["quotaIds"])
    assert all(row["token"] and row["expiresAt"] for row in leases)
    owner_expiry = run["ownerExpiresAt"]
    initial = {row["_id"]: row["expiresAt"] for row in leases}
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = database.agent_runs.find_one({"id": run_id, "status": "active"})
        leases = _lease_rows(database, run_id)
        current = {row["_id"]: row["expiresAt"] for row in leases}
        if _all_leases_renewed(run, owner_expiry, current, initial):
            return
        Event().wait(0.02)
    pytest.fail("real MongoDB owner and all quota leases were not renewed")


def _assert_completed_and_released(database, run_id: str) -> None:
    assert _await_status(database, run_id, "completed")["status"] == "completed"
    _await_released(database, run_id)


def _await_released(database, run_id: str | None = None) -> None:
    query = {"token": {"$exists": True}}
    if run_id:
        query["runId"] = run_id
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if database.ai_usage.count_documents(query) == 0:
            return
        Event().wait(0.02)
    pytest.fail("run did not release its quota lease")


def _ttl_deleted(database) -> int:
    return database.command("serverStatus")["metrics"]["ttl"]["deletedDocuments"]


def _await_ttl_deletion(database, quota_ids, before: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if database.ai_usage.count_documents({"_id": {"$in": quota_ids}}) == 0:
            if _ttl_deleted(database) > before:
                return
        Event().wait(0.02)
    pytest.fail("MongoDB TTL did not physically remove the expired quota rows")


def _await_run_leases(database, run_id: str) -> list[dict]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = _lease_rows(database, run_id)
        if len(rows) == 3:
            return rows
        Event().wait(0.02)
    pytest.fail("real MongoDB did not bind all quota leases to the Run")


def _assert_lost_worker_state(database, thread_id: str, run_id: str) -> None:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        run = database.agent_runs.find_one({"id": run_id}, {"_id": 0})
        assert run and run["status"] == "active"
        assert run["ownerId"] == "worker-takeover"
        assert _collection_counts(database, thread_id) == (1, 1, 2)
        Event().wait(0.02)
