"""真实 MongoDB replica set 上的最小单段修订 tracer：Artifact、正文、决定、事件原子一致。"""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("AGENT_TRACER_E2E_URL")
MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
SKILL_LOAD_MARK = "单段修订工作流"
pytestmark = pytest.mark.e2e("AGENT_TRACER_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def _login() -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    body = response.json()
    return client, body["csrfToken"]


def _csrf(client: httpx.Client, csrf: str) -> dict:
    return {"X-CSRF-Token": csrf}


def _document(*paragraphs: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
            for text in paragraphs
        ],
    }


PARAGRAPHS = ("第一段保持原样。", "第二段：教学目标需要更明确的评价依据。")
REPLACEMENT_MARK = "修订后的段落：教学目标、课堂任务与评价依据逐项对应"


def _create_case(client: httpx.Client, csrf: str) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": csrf},
        json={"title": f"tracer {uuid.uuid4().hex}", "document": _document(*PARAGRAPHS)},
    )
    assert response.status_code == 200
    return response.json()


def _thread(client: httpx.Client, case_id: str) -> dict:
    response = client.get(f"/api/cases/{case_id}/agent/thread")
    assert response.status_code == 200
    return response.json()


def _send(client: httpx.Client, csrf: str, case_id: str, text: str) -> httpx.Response:
    thread_id = _thread(client, case_id)["id"]
    return client.post(
        f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
        headers={"X-CSRF-Token": csrf},
        timeout=30,
        json={
            "id": "browser-chat-id",
            "trigger": "submit-message",
            "messages": [{
                "id": "client-message",
                "role": "user",
                "parts": [
                    {"type": "text", "text": text},
                    {"type": "data-skill", "data": {"skillId": "case-edit-skill"}},
                ],
            }],
        },
    )


def _await_artifact(database, thread_id: str) -> dict:
    deadline, wait = time.monotonic() + 30, Event()
    while time.monotonic() < deadline:
        artifact = database.agent_artifacts.find_one({"threadId": thread_id}, {"_id": 0})
        if artifact:
            return artifact
        wait.wait(0.05)
    pytest.fail("tracer run did not produce a pending artifact")


def _await_completed(database, thread_id: str) -> dict:
    deadline, wait = time.monotonic() + 30, Event()
    while time.monotonic() < deadline:
        run = database.agent_runs.find_one({"threadId": thread_id, "status": "completed"}, {"_id": 0})
        if run:
            return run
        wait.wait(0.05)
    pytest.fail("tracer run did not complete")


def _wait_for_catalog(client: httpx.Client) -> None:
    deadline, wait = time.monotonic() + 90, Event()
    while time.monotonic() < deadline:
        page = client.get("/api/search", params={"q": "科学家精神", "pageSize": 3}).json()
        if page.get("items"):
            return
        wait.wait(0.5)
    pytest.fail("e2e catalog never became searchable")


def _accept(client: httpx.Client, csrf: str, case_id: str, artifact_id: str):
    return client.post(
        f"/api/cases/{case_id}/agent/artifacts/{artifact_id}/decision",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "accepted"},
    )


def _assert_atomic_decision(database, case_id: str, artifact: dict) -> None:
    current = database.cases.find_one({"id": case_id}, {"_id": 0})
    assert current["revision"] == 2
    assert REPLACEMENT_MARK in current["document"]["content"][1]["content"][0]["text"]
    assert database.case_snapshots.count_documents(
        {"caseId": case_id, "kind": "pre_agent_decision"}
    ) == 1
    events = list(database.agent_thread_events.find(
        {"threadId": artifact["threadId"]}, {"_id": 0}
    ).sort("eventSeq", 1))
    assert [event["type"] for event in events].count("artifact.created") == 1
    assert [event["type"] for event in events].count("artifact.decided") == 1


def _tracer_case(client: httpx.Client, csrf: str, database) -> tuple[str, dict, dict]:
    _wait_for_catalog(client)
    case = _create_case(client, csrf)
    response = _send(client, csrf, case["id"], "请结合平台资料修订第2段：补充评价依据")
    assert response.status_code == 200, response.text
    thread_id = _thread(client, case["id"])["id"]
    run = _await_completed(database, thread_id)
    artifact = _await_artifact(database, thread_id)
    return case["id"], run, artifact


def _assert_skill_loaded(run: dict) -> None:
    kinds = {record["kind"]: record for record in run["resources"]}
    assert kinds["skill"]["id"] == "case-edit-skill"
    assert kinds["skill"]["version"] == "2.1"
    assert len(kinds["skill"]["contentHash"]) == 64


def test_tracer_run_builds_pending_artifact_with_server_sources():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        database = mongo.get_default_database()
        case_id, run, artifact = _tracer_case(client, csrf, database)
        _assert_skill_loaded(run)
        assert artifact["status"] == "pending"
        assert artifact["baseRevision"] == 1
        assert artifact["target"]["paragraphIndex"] == 1
        assert artifact["target"]["quote"] == PARAGRAPHS[1]
        assert artifact["sources"], "tracer artifact must cite at least one server source"
        current = database.cases.find_one({"id": case_id}, {"_id": 0})
        assert current["revision"] == 1
        assert current["document"] == _document(*PARAGRAPHS)
    finally:
        client.close()
        mongo.close()


def test_accept_writes_revision_snapshot_and_replays_decision():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        database = mongo.get_default_database()
        case_id, _run, artifact = _tracer_case(client, csrf, database)
        first = _accept(client, csrf, case_id, artifact["id"])
        assert first.status_code == 200, first.text
        duplicate = _accept(client, csrf, case_id, artifact["id"])
        assert duplicate.status_code == 200
        assert duplicate.json()["artifact"]["status"] == "accepted"
        _assert_atomic_decision(database, case_id, artifact)
        snapshot = client.get(f"/api/cases/{case_id}/agent/thread").json()
        assert [row["status"] for row in snapshot["artifacts"]] == ["accepted"]
        assert snapshot["latestRun"]["status"] == "completed"
    finally:
        client.close()
        mongo.close()


def _concurrent_accepts(client, csrf, case_id, artifact, database):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_accept, client, csrf, case_id, artifact["id"]) for _ in range(2)]
        responses = [future.result(timeout=30) for future in futures]
    assert [response.status_code for response in responses] == [200, 200]
    _assert_atomic_decision(database, case_id, artifact)


def test_concurrent_accept_writes_revision_exactly_once():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        database = mongo.get_default_database()
        case_id, _run, artifact = _tracer_case(client, csrf, database)
        _concurrent_accepts(client, csrf, case_id, artifact, database)
    finally:
        client.close()
        mongo.close()


def test_accept_rejects_stale_revision_on_real_replica_set():
    client, csrf = _login()
    mongo = MongoClient(MONGO_URI)
    try:
        database = mongo.get_default_database()
        case_id, _run, artifact = _tracer_case(client, csrf, database)
        changed = _document(*PARAGRAPHS[:1], "第二段已被作者手工改写。")
        patch = client.patch(
            f"/api/cases/{case_id}", headers={"X-CSRF-Token": csrf},
            json={"revision": 1, "document": changed},
        )
        assert patch.status_code == 200
        response = _accept(client, csrf, case_id, artifact["id"])
        assert response.status_code == 409
        assert database.agent_artifacts.find_one({"id": artifact["id"]})["status"] == "pending"
        assert database.cases.find_one({"id": case_id})["revision"] == 2
    finally:
        client.close()
        mongo.close()
