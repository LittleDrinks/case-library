from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from pymongo import MongoClient

from app.modules.agent.repository import AgentRepository


BASE_URL = os.environ.get("AGENT_CASE_LIBRARY_E2E_URL")
MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("AGENT_CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def _login(username: str = "user", password: str = "user123") -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return client, response.json()["csrfToken"]


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
        time.sleep(0.05)
    pytest.fail("real MongoDB run did not become active")


def _assert_terminal(snapshot: dict, events: list[dict]) -> None:
    assert snapshot["eventSeq"] == 4
    assert [message["messageSeq"] for message in snapshot["messages"]] == [1, 2]
    assert [message["role"] for message in snapshot["messages"]] == ["user", "assistant"]
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


def _paused_body(message_id: str, ready: Event, release: Event):
    payload = json.dumps(_body(message_id, "完成优先"), ensure_ascii=False).encode()

    def chunks():
        ready.set()
        if not release.wait(15):
            raise TimeoutError("real HTTP body was not released")
        yield payload

    return chunks()


def _hold_thread_write(database, thread_id: str):
    session = database.client.start_session()
    session.start_transaction()
    database.agent_threads.update_one(
        {"id": thread_id}, {"$set": {"probe": uuid.uuid4().hex}}, session=session
    )
    return session


def _submit_blocked_posts(
    pool, holder, holder_csrf, challenger, challenger_csrf, case, thread_id, release, ready
):
    requests = [
        (holder, holder_csrf, "real-retry-holder"),
        (challenger, challenger_csrf, "real-retry-challenger"),
    ]
    return [
        pool.submit(
            _send, client, csrf, case["id"], "完成优先", message_id,
            _paused_body(message_id, event, release), thread_id=thread_id,
        )
        for (client, csrf, message_id), event in zip(requests, ready)
    ]


def _blocked_posts(holder, holder_csrf, challenger, challenger_csrf, case, thread_id, session):
    release = Event()
    ready = (Event(), Event())
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = _submit_blocked_posts(
            pool, holder, holder_csrf, challenger, challenger_csrf, case, thread_id, release, ready
        )
        assert all(event.wait(5) for event in ready)
        time.sleep(0.5)
        release.set()
        time.sleep(0.5)
        session.abort_transaction()
        return [future.result(timeout=15) for future in futures]


def _completion_first_overlap(holder, holder_csrf, challenger, challenger_csrf, case, database):
    thread_id = _thread(holder, case["id"])["id"]
    session = _hold_thread_write(database, thread_id)
    try:
        responses = _blocked_posts(
            holder, holder_csrf, challenger, challenger_csrf, case, thread_id, session
        )
    finally:
        if session.in_transaction:
            session.abort_transaction()
        session.end_session()
    return thread_id, responses


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


def _terminal_changes(stream, thread_id: str) -> list[tuple[str, str]]:
    changes = []
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and len(changes) < 3:
        change = stream.try_next()
        label = _change_label(change, thread_id) if change else None
        if label and label[0] not in [item[0] for item in changes]:
            changes.append(label)
        if not change:
            time.sleep(0.01)
    if len(changes) != 3:
        pytest.fail(f"Change Stream did not expose terminal order: {changes}")
    return changes


def _assert_change_order(changes: list[tuple[str, str]]) -> None:
    assert [label for label, _run_id in changes] == [
        "assistant-message", "terminal-run", "terminal-event"
    ]
    assert len({run_id for _label, run_id in changes}) == 1


def test_agent_http_real_replica_set_rejects_completion_first_transaction_retry():
    holder, holder_csrf = _login()
    challenger, challenger_csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        case = _create_case(holder, holder_csrf)
        database = mongo.get_default_database()
        thread_id, responses = _completion_first_overlap(
            holder, holder_csrf, challenger, challenger_csrf, case, database
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json() == {"detail": "当前对话已有运行任务"}
        snapshot = _thread(holder, case["id"])
        _assert_terminal(snapshot, _events(database, thread_id))
        _assert_thread_counts(database, thread_id)
    finally:
        _close(holder, challenger, mongo=mongo)


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
            response = _send(
                client, csrf, case["id"], "Change Stream 顺序", "real-order", thread_id=thread_id
            )
            changes = _terminal_changes(stream, thread_id)
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
