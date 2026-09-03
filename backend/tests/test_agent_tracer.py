"""最小单段修订 tracer：生产 Agent + Skill 按需加载 + Artifact 领域路径。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.modules.agent.runtime import agent
from app.modules.agent.resources import CASE_EDIT_SKILL
from app.modules.agent.tracer import REPLACEMENT, SKILL_ID, tracer_model
from app.modules.search.meilisearch import CatalogPage

CASES_PATH = "/api/cases"
SKILL_BODY_MARK = "单段修订工作流 v2.1"


class StubCatalog:
    """返回固定命中目录替身：只满足 search 协议，权限过滤由真实服务完成。"""

    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def health(self, *_args) -> None:
        return None

    def search(self, _request) -> CatalogPage:
        return CatalogPage(list(self.items), None, False, False)


def _login(client: TestClient, username: str = "user", password: str = "user123") -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _document(*paragraphs: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
            for text in paragraphs
        ],
    }


def _create_case(client: TestClient, auth: dict, *paragraphs: str) -> dict:
    response = client.post(
        CASES_PATH,
        headers=_csrf(auth),
        json={"title": "tracer 案例", "document": _document(*paragraphs)},
    )
    assert response.status_code == 200
    return response.json()


def _thread_path(case_id: str) -> str:
    return f"{CASES_PATH}/{case_id}/agent/thread"


def _message_parts(text: str, skill_id: str | None = SKILL_ID) -> list[dict]:
    parts = [{"type": "text", "text": text}]
    if skill_id:
        parts.append({"type": "data-skill", "data": {"skillId": skill_id}})
    return parts


def _send(client: TestClient, auth: dict, case_id: str, text: str, model=None,
          skill_id: str | None = SKILL_ID):
    with agent.override(model=model or tracer_model()):
        thread_id = client.get(_thread_path(case_id)).json()["id"]
        return client.post(
            f"{_thread_path(case_id)}/{thread_id}/stream",
            headers=_csrf(auth),
            json={
                "id": "browser-chat-id",
                "trigger": "submit-message",
                "messages": [{
                    "id": "client-message", "role": "user",
                    "parts": _message_parts(text, skill_id),
                }],
            },
        )


def _artifact(database, thread_id: str) -> dict:
    return database.agent_artifacts.find_one({"threadId": thread_id}, {"_id": 0})


HIT = {
    "id": "c-42", "kind": "case", "title": "科学家精神融入课堂",
    "summary": "以科学家精神为主题的教学案例，含教学目标与评价量规。",
}
PARAGRAPHS = ("第一段保持不变。", "第二段：教学目标需要更明确的评价依据。")


@pytest.fixture
def tracer_case(client: TestClient) -> dict:
    client.app.state.search_catalog = StubCatalog([HIT])
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    with agent.override(model=tracer_model()):
        response = _send(client, auth, case["id"], "请结合平台资料修订第2段：补充评价依据")
    assert response.status_code == 200, response.text
    return case


def _assert_pending_artifact(client: TestClient, case: dict) -> dict:
    database = client.app.state.database
    thread_id = client.get(_thread_path(case["id"])).json()["id"]
    artifact = _artifact(database, thread_id)
    assert artifact["status"] == "pending"
    assert artifact["baseRevision"] == 1
    assert artifact["target"]["paragraphIndex"] == 1
    assert artifact["target"]["quote"] == PARAGRAPHS[1]
    assert artifact["replacement"] == REPLACEMENT
    assert artifact["sources"] == [{
        "kind": "case", "id": HIT["id"], "title": HIT["title"], "snippet": HIT["summary"],
    }]
    current = database.cases.find_one({"id": case["id"]}, {"_id": 0})
    assert current["revision"] == 1 and current["document"] == _document(*PARAGRAPHS)
    return artifact


def test_tracer_creates_pending_artifact_without_touching_body(client: TestClient, tracer_case) -> None:
    _assert_pending_artifact(client, tracer_case)
    snapshot = client.get(_thread_path(tracer_case["id"])).json()
    tool_parts = [
        part
        for message in snapshot["messages"]
        for part in message["parts"]
        if part["type"].startswith("tool-")
    ]
    assert [part["type"] for part in tool_parts] == [
        "tool-load_capability", "tool-search_corpus", "tool-propose_revision",
    ]
    assert tool_parts[1]["output"]["sources"][0]["id"] == HIT["id"]
    assert tool_parts[2]["output"]["artifactId"]


def test_run_records_resource_id_version_and_hash(client: TestClient, tracer_case) -> None:
    database = client.app.state.database
    run = database.agent_runs.find_one({}, {"_id": 0})
    kinds = {record["kind"]: record for record in run["resources"]}
    assert set(kinds) == {"system-prompt", "task-prompt", "skill"}
    assert kinds["skill"]["id"] == SKILL_ID
    assert kinds["skill"]["version"] == "2.1"
    assert len(kinds["skill"]["contentHash"]) == 64
    assert kinds["system-prompt"]["contentHash"]


def test_skill_body_enters_context_only_after_load(client: TestClient) -> None:
    calls: list = []

    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    response = _send(client, auth, case["id"], "请修订第2段", model=tracer_model(calls.append))
    assert response.status_code == 200, response.text
    flattened = [str(part) for message in calls[0] for part in message.parts]
    assert not any(SKILL_BODY_MARK in text for text in flattened)
    later = [str(part) for message in calls[-1] for part in message.parts]
    assert any(SKILL_BODY_MARK in text for text in later)
    assert len(calls) >= 3


def _decide(client: TestClient, case_id: str, artifact_id: str, decision: str):
    body = {"decision": decision}
    headers = _csrf(_login(client))
    return client.post(
        f"{CASES_PATH}/{case_id}/agent/artifacts/{artifact_id}/decision",
        headers=headers, json=body,
    )


def test_accept_writes_revision_once_and_replays_decision(client: TestClient, tracer_case) -> None:
    artifact = _assert_pending_artifact(client, tracer_case)
    first = _decide(client, tracer_case["id"], artifact["id"], "accepted")
    assert first.status_code == 200, first.text
    duplicate = _decide(client, tracer_case["id"], artifact["id"], "accepted")
    assert duplicate.status_code == 200
    assert duplicate.json()["artifact"]["status"] == "accepted"
    database = client.app.state.database
    case_id = tracer_case["id"]
    current = database.cases.find_one({"id": case_id}, {"_id": 0})
    assert current["revision"] == 2
    assert REPLACEMENT in current["document"]["content"][1]["content"][0]["text"]
    assert database.case_snapshots.count_documents(
        {"caseId": case_id, "kind": "pre_agent_decision"}
    ) == 1
    decided = _decided_events(database, case_id)
    assert len(decided) == 1 and decided[0]["payload"]["decision"] == "accepted"


def _decided_events(database, case_id: str) -> list[dict]:
    thread_id = client_thread(database, case_id)
    events = database.agent_thread_events.find({"threadId": thread_id})
    return [event for event in events if event["type"] == "artifact.decided"]


def client_thread(database, case_id: str) -> str:
    return database.agent_threads.find_one({"caseId": case_id})["id"]


def test_accept_fails_after_body_changed(client: TestClient, tracer_case) -> None:
    artifact = _assert_pending_artifact(client, tracer_case)
    case_id = tracer_case["id"]
    headers = _csrf(_login(client))
    changed = _document(*PARAGRAPHS[:1], "第二段已被作者手工改写。")
    patch = client.patch(
        f"{CASES_PATH}/{case_id}", headers=headers,
        json={"revision": 1, "document": changed},
    )
    assert patch.status_code == 200
    assert _decide(client, case_id, artifact["id"], "accepted").status_code == 409
    assert client.app.state.database.agent_artifacts.find_one(
        {"id": artifact["id"]}
    )["status"] == "pending"


def test_accept_fails_when_quote_no_longer_matches(client: TestClient, tracer_case) -> None:
    artifact = _assert_pending_artifact(client, tracer_case)
    case_id = tracer_case["id"]
    changed = _document(*PARAGRAPHS[:1], "第二段悄悄变了。")
    client.app.state.database.cases.update_one(
        {"id": case_id, "revision": 1}, {"$set": {"document": changed}}
    )
    assert _decide(client, case_id, artifact["id"], "accepted").status_code == 409
    assert client.app.state.database.cases.find_one({"id": case_id})["revision"] == 1


def test_non_author_cannot_decide_artifact(client: TestClient, tracer_case) -> None:
    artifact = _assert_pending_artifact(client, tracer_case)
    case_id = tracer_case["id"]
    admin = _login(client, "admin", "admin123")
    body = {"decision": "accepted"}
    response = client.post(
        f"{CASES_PATH}/{case_id}/agent/artifacts/{artifact['id']}/decision",
        headers=_csrf(admin), json=body,
    )
    assert response.status_code == 403
    assert client.app.state.database.cases.find_one({"id": case_id})["revision"] == 1


def test_reject_keeps_body_and_records_decision(client: TestClient, tracer_case) -> None:
    artifact = _assert_pending_artifact(client, tracer_case)
    case_id = tracer_case["id"]
    assert _decide(client, case_id, artifact["id"], "rejected").status_code == 200
    database = client.app.state.database
    current = database.cases.find_one({"id": case_id}, {"_id": 0})
    assert current["revision"] == 1 and current["document"] == _document(*PARAGRAPHS)
    assert database.case_snapshots.count_documents({"caseId": case_id}) == 0
    assert database.agent_artifacts.find_one({"id": artifact["id"]})["status"] == "rejected"


def test_snapshot_restores_artifact_and_decision(client: TestClient, tracer_case) -> None:
    artifact = _assert_pending_artifact(client, tracer_case)
    case_id = tracer_case["id"]
    assert _decide(client, case_id, artifact["id"], "accepted").status_code == 200
    snapshot = client.get(_thread_path(case_id)).json()
    assert [row["id"] for row in snapshot["artifacts"]] == [artifact["id"]]
    assert snapshot["artifacts"][0]["status"] == "accepted"
    assert snapshot["latestRun"]["status"] == "completed"
    resources = {row["kind"] for row in snapshot["latestRun"]["resources"]}
    assert resources == {"system-prompt", "task-prompt", "skill"}


def test_skill_manifest_matches_registered_resource() -> None:
    text = CASE_EDIT_SKILL.read()
    assert text.startswith("---\nid: case-edit-skill\nversion: 2.1\n")
    assert SKILL_BODY_MARK in text


def test_forged_skill_name_rejected_before_run(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    response = _send(client, auth, case["id"], "伪造能力", skill_id="fake-skill")
    assert response.status_code == 422
    database = client.app.state.database
    assert database.agent_runs.count_documents({}) == 0
    assert database.agent_messages.count_documents({}) == 0
