from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from app.modules.agent import agent, prosemirror
from app.modules.agent.artifacts import decide_artifact, propose_artifact
from app.modules.agent.models import ArtifactTarget, SourceRef
from app.modules.agent.repository import AgentRepository
from app.modules.agent.source_reader import read_source
from app.modules.cases.service import CaseError


def _document(*text: str) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": item}]}
        for item in text
    ]}


def _auth(client: TestClient) -> dict:
    return client.post("/api/auth/login", json={"username": "user", "password": "user123"}).json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _seed_source(database, public: str = "public") -> None:
    database.cases.insert_one({
        "id": "c-source-22", "ownerId": "other", "publicationStatus": public,
        "workflowStatus": "published", "publishedVersionId": "v-source-22",
    })
    database.case_versions.insert_one({
        "id": "v-source-22", "caseId": "c-source-22", "number": 4,
        "title": "固定来源", "document": _document("固定版本正文"),
    })
    database.case_sources.insert_one({
        "id": "src-22", "caseId": "c-draft-1", "sourceCaseId": "c-source-22",
        "versionId": "v-source-22", "versionNumber": 4, "title": "固定来源",
    })


def _post_parts(client: TestClient, auth: dict, case_id: str, parts: list[dict]):
    thread = client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]
    body = {"id": "source-context", "trigger": "submit-message",
            "messages": [{"id": "source-message", "role": "user", "parts": parts}]}
    with agent.override(model=TestModel(custom_output_text="完成", call_tools=[])):
        return client.post(f"/api/cases/{case_id}/agent/thread/{thread}/stream",
                           headers=_csrf(auth), json=body)


def test_read_source_returns_fixed_version_and_location(client: TestClient) -> None:
    _seed_source(client.app.state.database)
    result = read_source(client.app.state.database, None, {"id": "u-user-demo", "role": "user"},
                         "c-draft-1", "case", "src-22")
    assert result["status"] == "ok"
    assert result["usedSourceRef"]["versionId"] == "v-source-22"
    assert result["usedSourceRef"]["location"] == "case:c-source-22@v-source-22"


def test_read_source_rechecks_source_publication(client: TestClient) -> None:
    _seed_source(client.app.state.database, "private")
    result = read_source(client.app.state.database, None, {"id": "u-user-demo", "role": "user"},
                         "c-draft-1", "case", "src-22")
    assert result == {"status": "no_access", "detail": "来源案例内容当前不可读"}


def test_forged_source_part_is_rejected_before_run(client: TestClient) -> None:
    auth = _auth(client)
    response = _post_parts(client, auth, "c-draft-1", [
        {"type": "text", "text": "请使用来源"},
        {"type": "data-source", "data": {"sourceType": "case", "id": "src-forged"}},
    ])
    assert response.status_code == 422
    assert client.app.state.database.agent_runs.count_documents({}) == 0


def test_selection_and_source_parts_are_persisted_structurally(client: TestClient) -> None:
    auth = _auth(client)
    case = client.post("/api/cases", headers=_csrf(auth), json={
        "title": "上下文案例", "document": _document("第一段", "第二段"),
    }).json()
    response = _post_parts(client, auth, case["id"], [
        {"type": "text", "text": "请查看第二段"},
        {"type": "data-selection", "data": {"from": 1, "to": 4, "quote": "第二段"}},
    ])
    assert response.status_code == 200
    message = client.app.state.database.agent_messages.find_one({"role": "user"})
    assert message["parts"][1]["type"] == "data-selection"


def _evidence_artifact(database, user: dict):
    repository = AgentRepository(database)
    thread = repository.default_thread("c-draft-1", user["id"])
    case = database.cases.find_one({"id": "c-draft-1"})
    block = prosemirror.text_blocks(case["document"])[0]
    target = ArtifactTarget(from_pos=block["start"], to_pos=block["end"], quote=prosemirror.text_between(case["document"], block["start"], block["end"]))
    run = repository.start_run(
        thread, user["id"], [{"type": "text", "text": "修订"}], {}, "assistant-22",
        base_revision=case["revision"], target=target,
    )
    ref = SourceRef(kind="case", id="src-22", title="固定来源", version_id="v-source-22",
                    location="case:c-source-22@v-source-22")
    artifact = propose_artifact(
        database, "c-draft-1", thread.id, run.id, target.from_pos, target.to_pos,
        "替换", "理由", [ref], user,
    )
    database.agent_artifacts.insert_one(artifact.model_dump(by_alias=True, mode="python"))
    return thread, artifact


def test_accept_rechecks_evidence_permissions(client: TestClient) -> None:
    database = client.app.state.database
    _seed_source(database)
    user = {"id": "u-user-demo", "role": "user"}
    thread, artifact = _evidence_artifact(database, user)
    database.agent_runs.update_one({"id": artifact.run_id}, {"$set": {"status": "completed"}})
    database.cases.update_one({"id": "c-source-22"}, {"$set": {"publicationStatus": "private"}})
    with pytest.raises(CaseError, match="依据当前不可读"):
        decide_artifact(database, "c-draft-1", thread.id, artifact.id, user, "accepted")
