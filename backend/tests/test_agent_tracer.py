"""最小单段修订 tracer：生产 Agent + 已发布 Skill 按需加载 + Artifact 领域路径。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from app.modules.agent.runtime import agent
from tests.agent_tracer import REPLACEMENT, tracer_model, tracer_response
from tests.skill_packages import EXAMPLE_PATH, EXAMPLE_TEXT, SKILL_ID, build_package
from app.modules.search.meilisearch import CatalogPage

CASES_PATH = "/api/cases"
SKILL_BODY_MARK = "写作前至少通读一个范例"


def test_tracer_reads_the_actual_search_result():
    messages = [
        ModelResponse(parts=[ToolCallPart("search_corpus", {"query": "科学家精神"})]),
        ModelRequest(parts=[ToolReturnPart("search_corpus", {"sources": [
            {"kind": "case", "id": "actual-published-case"},
        ]})]),
    ]
    call = tracer_response(messages).parts[0]
    assert call.tool_name == "read_source"
    assert call.args_as_dict() == {"source_type": "case", "source_id": "actual-published-case"}


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
    parts = [{"type": "text", "text": text}, {
        "type": "data-selection",
        "data": {"from": SELECTION[0], "to": SELECTION[1]},
    }]
    if skill_id:
        parts.append({"type": "data-skill", "data": {"skillId": skill_id}})
    return parts


def _send(client: TestClient, auth: dict, case_id: str, text: str, model=None,
          skill_id: str | None = SKILL_ID):
    with agent.override(model=model or _tracer()):
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
# Native Tiptap/ProseMirror positions for the second paragraph: 11..30.
SELECTION = (11, 30)


def _seed_source_case(database) -> None:
    """检索命中来源落库为真实已发布案例，供接受前证据复验。"""
    database.cases.insert_one({
        "id": HIT["id"], "ownerId": "u-source", "publicationStatus": "public",
        "workflowStatus": "published", "publishedVersionId": "hit-v1",
        "revision": 1, "title": HIT["title"],
        "document": {"type": "doc", "content": []},
    })
    database.case_versions.insert_one({
        "id": "hit-v1", "caseId": HIT["id"], "number": 1, "title": HIT["title"],
        "document": _document("平台资料正文"),
    })


def _tracer():
    return tracer_model(skill_id=SKILL_ID, selection=SELECTION)


def _publish_skill(client: TestClient) -> dict:
    """管理员上传并发布 v2.1 用户包，返回版本凭据。"""
    admin = _login(client, "admin", "admin123")
    response = client.post(
        "/api/admin/skills/packages", headers=_csrf(admin),
        files={"file": ("skill.zip", build_package(), "application/zip")},
    )
    assert response.status_code == 201, response.text
    version = response.json()["version"]
    publish = client.post(
        f"/api/admin/skills/{SKILL_ID}/publish", headers=_csrf(admin),
        json={"versionId": version["id"]},
    )
    assert publish.status_code == 200, publish.text
    return version


@pytest.fixture
def tracer_case(client: TestClient) -> dict:
    client.app.state.search_catalog = StubCatalog([HIT])
    _seed_source_case(client.app.state.database)
    _publish_skill(client)
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    with agent.override(model=_tracer()):
        response = _send(client, auth, case["id"], "请结合平台资料修订第2段：补充评价依据")
    assert response.status_code == 200, response.text
    return case


def _assert_pending_artifact(client: TestClient, case: dict) -> dict:
    database = client.app.state.database
    thread_id = client.get(_thread_path(case["id"])).json()["id"]
    artifact = _artifact(database, thread_id)
    assert artifact["status"] == "pending"
    assert artifact["baseRevision"] == 1
    assert artifact["target"]["from"] == SELECTION[0]
    assert artifact["target"]["to"] == SELECTION[1]
    assert artifact["target"]["quote"] == PARAGRAPHS[1]
    assert artifact["replacement"] == REPLACEMENT
    assert artifact["sources"] == [{
        "kind": "case", "id": HIT["id"], "title": HIT["title"], "snippet": "",
        "version": "v1", "versionId": "hit-v1", "location": "case:c-42@hit-v1",
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
        "tool-load_capability", "tool-read_skill_resource_sizheng_case_generator",
        "tool-search_corpus", "tool-read_source", "tool-propose_revision",
    ]
    assert tool_parts[1]["output"] == {"path": EXAMPLE_PATH, "content": EXAMPLE_TEXT}
    assert tool_parts[3]["output"]["usedSourceRef"]["id"] == HIT["id"]
    assert tool_parts[3]["output"]["content"] == "平台资料正文"
    assert tool_parts[4]["output"]["artifactId"]


def test_run_records_resource_id_and_hash(client: TestClient, tracer_case) -> None:
    database = client.app.state.database
    run = database.agent_runs.find_one({}, {"_id": 0})
    version = database.skill_versions.find_one({"skillId": SKILL_ID}, {"_id": 0})
    kinds = {record["kind"]: record for record in run["resources"]}
    assert kinds["skill"] == {
        "kind": "skill", "id": SKILL_ID,
        "version": version["version"], "contentHash": version["packageSha256"],
    }
    assert kinds["system-prompt"]["contentHash"]
    timings = list(run["toolTimings"].values())
    assert {timing["toolName"] for timing in timings} == {
        "load_capability", "read_skill_resource_sizheng_case_generator",
        "search_corpus", "read_source", "propose_revision",
    }
    assert all(timing.get("startedAt") and timing.get("finishedAt") for timing in timings)


def test_reopen_redacts_sources_that_lost_access(client: TestClient, tracer_case) -> None:
    database = client.app.state.database
    database.cases.update_one({"id": HIT["id"]}, {"$set": {"publicationStatus": "private"}})
    snapshot = client.get(_thread_path(tracer_case["id"])).json()
    parts = [part for message in snapshot["messages"] for part in message["parts"]]
    read = next(part for part in parts if part["type"] == "tool-read_source")
    search = next(part for part in parts if part["type"] == "tool-search_corpus")
    assert read["output"] == {"status": "no_access", "detail": "来源当前不可读"}
    assert search["output"]["sources"] == []


def test_run_binds_selected_published_skill(client: TestClient) -> None:
    client.app.state.search_catalog = StubCatalog([HIT])
    _publish_skill(client)
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    _seed_source_case(client.app.state.database)
    response = _send(
        client, auth, case["id"], "请使用能力修订第2段",
        model=tracer_model(skill_id=SKILL_ID, selection=SELECTION), skill_id=SKILL_ID,
    )
    assert response.status_code == 200, response.text
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    version = client.app.state.database.skill_versions.find_one({"skillId": SKILL_ID})
    assert run["skillBindings"] == [{"kind": "skill", "id": SKILL_ID,
                                     "versionId": version["id"], "version": version["version"]}]
    assert {row["kind"] for row in run["resources"]} == {"system-prompt", "task-prompt", "skill"}


def _assert_delayed_skill(calls: list) -> None:
    first_messages, first_instructions = calls[0]
    flattened = [str(part) for message in first_messages for part in message.parts]
    assert not any(SKILL_BODY_MARK in text for text in flattened)
    assert "load_capability" in first_instructions
    later_messages = [str(part) for message in calls[-1][0] for part in message.parts]
    assert any(SKILL_BODY_MARK in text for text in later_messages)
    assert all(SKILL_BODY_MARK not in instructions for _messages, instructions in calls)
    assert len(calls) >= 3


def test_skill_body_enters_context_only_after_load(client: TestClient) -> None:
    calls: list = []

    def recorder(messages, info):
        calls.append((messages, info.instructions or ""))

    client.app.state.search_catalog = StubCatalog([HIT])
    _publish_skill(client)
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    response = _send(
        client, auth, case["id"], "请修订第2段",
        model=tracer_model(recorder, skill_id=SKILL_ID, selection=SELECTION),
    )
    assert response.status_code == 200, response.text
    _assert_delayed_skill(calls)

def _decide(client: TestClient, case_id: str, artifact_id: str, decision: str,
            thread_id: str | None = None):
    if thread_id is None:
        thread_id = client.get(_thread_path(case_id)).json()["id"]
    body = {"decision": decision}
    headers = _csrf(_login(client))
    return client.post(
        f"{CASES_PATH}/{case_id}/agent/thread/{thread_id}"
        f"/artifacts/{artifact_id}/decision",
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
    thread_id = client_thread(client.app.state.database, case_id)
    admin = _login(client, "admin", "admin123")
    body = {"decision": "accepted"}
    response = client.post(
        f"{CASES_PATH}/{case_id}/agent/thread/{thread_id}"
        f"/artifacts/{artifact['id']}/decision",
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


def test_forged_skill_name_rejected_before_run(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    response = _send(client, auth, case["id"], "伪造能力", skill_id="fake-skill")
    assert response.status_code == 422
    database = client.app.state.database
    assert database.agent_runs.count_documents({}) == 0
    assert database.agent_messages.count_documents({}) == 0
