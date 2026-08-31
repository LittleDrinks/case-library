from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from pymongo import MongoClient

from app.modules.agent.repository import AgentRepository


BASE_URL = os.environ.get("AGENT_CASE_LIBRARY_E2E_URL")
MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("AGENT_CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def _login() -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
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


def _send(client: httpx.Client, csrf: str, case_id: str, text: str, message_id: str):
    thread_id = _thread(client, case_id)["id"]
    return client.post(
        f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
        headers={"X-CSRF-Token": csrf},
        json=_body(message_id, text),
        timeout=15,
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
    assert snapshot["latestRun"]["status"] == "completed"
    assert [event["eventSeq"] for event in events] == [1, 2, 3, 4]
    assert [event["type"] for event in events] == [
        "message.created", "run.started", "message.created", "run.completed"
    ]


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
