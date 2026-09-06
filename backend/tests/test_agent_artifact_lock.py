"""#37 Artifact 安全：Run 锁定目标/基线、决定门禁、过期展示与证据复验。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.modules.agent import artifacts
from app.modules.agent.models import AgentMessage, ArtifactTarget, SourceRef
from app.modules.agent.repository import AgentRepository
from app.modules.cases.service import CaseError

PARAGRAPHS = ("第一段保持不变。", "第二段需要修订。")
REPLACEMENT = "第二段已按来源修订。"
SELECTION = {"type": "data-selection", "data": {"paragraphIndex": 1, "quote": PARAGRAPHS[1]}}


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _document(*paragraphs: str) -> dict:
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        for text in paragraphs
    ]}


def _create_case(client: TestClient, auth: dict, *paragraphs: str) -> dict:
    response = client.post(
        "/api/cases", headers=_csrf(auth),
        json={"title": "锁目标案例", "document": _document(*paragraphs)},
    )
    assert response.status_code == 200
    return response.json()


def _send(client: TestClient, auth: dict, case_id: str, parts: list[dict]) -> dict:
    from pydantic_ai.models.test import TestModel

    from app.modules.agent.runtime import agent

    thread_id = client.get(f"/api/cases/{case_id}/agent/thread").json()["id"]
    with agent.override(model=TestModel(call_tools=[], custom_output_text="好的")):
        response = client.post(
            f"/api/cases/{case_id}/agent/thread/{thread_id}/stream",
            headers=_csrf(auth),
            json={"id": "browser", "trigger": "submit-message",
                  "messages": [{"id": "m1", "role": "user", "parts": parts}]},
        )
    assert response.status_code == 200, response.text
    return response


def _run_row(database, case_id: str) -> dict:
    thread_id = database.agent_threads.find_one({"caseId": case_id})["id"]
    return database.agent_runs.find_one({"threadId": thread_id}, {"_id": 0})


# ---- Run 创建即锁定 baseRevision 与目标段 ----


def test_run_locks_base_revision_and_selected_target(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    _send(client, auth, case["id"], [
        {"type": "text", "text": "请修订选中的段落"}, SELECTION,
    ])
    run = _run_row(client.app.state.database, case["id"])
    assert run["baseRevision"] == 1
    assert run["target"] == {"paragraphIndex": 1, "quote": PARAGRAPHS[1]}


def test_single_paragraph_document_locks_that_paragraph(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, "唯一段落。")
    _send(client, auth, case["id"], [{"type": "text", "text": "请修订"}])
    run = _run_row(client.app.state.database, case["id"])
    assert run["baseRevision"] == 1
    assert run["target"] == {"paragraphIndex": 0, "quote": "唯一段落。"}


def test_multi_paragraph_without_selection_locks_no_target(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    _send(client, auth, case["id"], [{"type": "text", "text": "请修订"}])
    run = _run_row(client.app.state.database, case["id"])
    assert run["baseRevision"] == 1
    assert run.get("target") is None


# ---- 提议必须命中锁 ----


def _locked_run(client: TestClient, auth: dict, case: dict, paragraph_index: int = 1):
    """直接构造锁定 Run（保持 active，供各决定场景自行推进终态）。"""
    database = client.app.state.database
    repository = AgentRepository(database)
    thread = repository.default_thread(case["id"], auth["user"]["id"])
    run = repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "修订"}], {},
        "assistant-lock", base_revision=case["revision"],
        target=ArtifactTarget(
            paragraph_index=paragraph_index, quote=PARAGRAPHS[paragraph_index],
        ),
    )
    return database, repository, thread, run


def _propose(database, case: dict, run, paragraph_index: int = 1, sources=()):
    return artifacts.propose_artifact(
        database, case["id"], run.thread_id, run.id, paragraph_index,
        REPLACEMENT, "依据来源", list(sources), _owner(database, case),
    )


def _owner(database, case: dict) -> dict:
    row = database.cases.find_one({"id": case["id"]}, {"ownerId": 1})
    return {"id": row["ownerId"], "role": "user"}


def test_propose_without_locked_target_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, _repository, _thread, run = _locked_run(client, auth, case)
    database.agent_runs.update_one({"id": run.id}, {"$set": {"target": None}})
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run)
    assert excinfo.value.status_code == 422
    assert database.agent_artifacts.count_documents({}) == 0


def test_propose_off_locked_paragraph_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, _repository, _thread, run = _locked_run(client, auth, case)
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run, paragraph_index=0)
    assert excinfo.value.status_code == 422
    assert database.agent_artifacts.count_documents({}) == 0


def test_propose_after_baseline_revision_change_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, _repository, _thread, run = _locked_run(client, auth, case)
    database.cases.update_one({"id": case["id"]}, {"$set": {"revision": 2}})
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run)
    assert excinfo.value.status_code == 409
    assert database.agent_artifacts.count_documents({}) == 0


def test_only_one_proposal_per_run(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, _repository, _thread, run = _locked_run(client, auth, case)
    first = _propose(database, case, run)
    assert first.status == "pending"
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run)
    assert excinfo.value.status_code == 409
    assert database.agent_artifacts.count_documents({"runId": run.id}) == 1


# ---- 决定门禁：运行终态、取消/失败、重复相反决定 ----


def test_decide_refused_until_run_reaches_terminal(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, repository, thread, run = _locked_run(client, auth, case)
    artifact = _propose(database, case, run)
    with pytest.raises(CaseError) as active_error:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
        )
    assert active_error.value.status_code == 409
    assert database.agent_artifacts.find_one({"id": artifact.id})["status"] == "pending"
    assert repository.complete_run(run.id, _assistant_message(run), resources=[]) is True
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert result["artifact"].status == "accepted"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 2


def _assistant_message(run):
    return AgentMessage(
        id=f"assistant-{run.id}", thread_id=run.thread_id, run_id=run.id,
        role="assistant", parts=[{"type": "text", "text": "完成"}],
        created_at=datetime.now(UTC),
    )


def test_cancelled_run_proposal_cannot_be_accepted(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, repository, thread, run = _locked_run(client, auth, case)
    artifact = _propose(database, case, run)
    assert repository.cancel_run(run.id) is True
    with pytest.raises(CaseError) as excinfo:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
        )
    assert excinfo.value.status_code == 409
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1
    rejected = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "rejected",
    )
    assert rejected["artifact"].status == "rejected"


def test_repeat_same_decision_replays_opposite_conflicts(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, _repository, thread, run = _locked_run(client, auth, case)
    artifact = _propose(database, case, run)
    database.agent_runs.update_one({"id": run.id}, {"$set": {"status": "completed"}})
    first = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    replay = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert first["artifact"].status == replay["artifact"].status == "accepted"
    with pytest.raises(CaseError) as excinfo:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "rejected",
        )
    assert excinfo.value.status_code == 409
    assert database.cases.find_one({"id": case["id"]})["revision"] == 2


# ---- 基线过期：读取侧展示 expired，接受被拒 ----


def test_revision_change_marks_expired_and_blocks_accept(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, *PARAGRAPHS)
    database, repository, thread, run = _locked_run(client, auth, case)
    artifact = _propose(database, case, run)
    assert repository.complete_run(run.id, _assistant_message(run), resources=[]) is True
    database.cases.update_one({"id": case["id"]}, {"$set": {"revision": 2}})
    snapshot = repository.snapshot(thread)
    assert snapshot.artifacts[0].status == "expired"
    with pytest.raises(CaseError) as excinfo:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
        )
    assert excinfo.value.status_code == 409
    assert database.agent_artifacts.find_one({"id": artifact.id})["status"] == "pending"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 2


# ---- 证据复验：权限、发布状态与来源下线 ----


def _seed_case_source(database) -> None:
    database.cases.insert_one({
        "id": "c-src", "ownerId": "u-other", "publicationStatus": "public",
        "workflowStatus": "published", "publishedVersionId": "cv-1", "revision": 1,
        "title": "来源案例", "document": {"type": "doc", "content": []},
    })
    database.case_versions.insert_one({
        "id": "cv-1", "caseId": "c-src", "number": 1, "title": "来源案例 v1",
        "document": {"type": "doc", "content": []},
    })


CASE_SOURCE = SourceRef(kind="case", id="c-src", title="来源案例 v1")
KNOWLEDGE_SOURCE = SourceRef(kind="knowledge", id="ks-1", title="教材章节")
MATERIAL_SOURCE = SourceRef(kind="material", id="m-1", title="公开素材")


def _seed_knowledge(database) -> None:
    database.knowledge_sections.insert_one({"id": "ks-1", "sourceId": "kn-1"})
    database.knowledge_sources.insert_one({"id": "kn-1", "status": "active"})


def _seed_material(database) -> None:
    database.materials.insert_one({
        "id": "m-1", "status": "active", "accessLevel": "public", "title": "公开素材",
    })


def _seed_evidence_case(client: TestClient, auth: dict, sources: list[SourceRef]):
    """构造完成态 Run + 引用来源的 pending Artifact，供接受复验。"""
    case = _create_case(client, auth, *PARAGRAPHS)
    database, repository, thread, run = _locked_run(client, auth, case)
    artifact = _propose(database, case, run, sources=sources)
    assert repository.complete_run(run.id, _assistant_message(run), resources=[]) is True
    return database, case, thread, artifact


def _refused_accept(database, case, thread, artifact, auth):
    with pytest.raises(CaseError) as excinfo:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
        )
    return excinfo


def test_accept_rechecks_case_source_permission_and_publication(client: TestClient) -> None:
    auth = _login(client)
    database = client.app.state.database
    _seed_case_source(database)
    database, case, thread, artifact = _seed_evidence_case(client, auth, [CASE_SOURCE])
    database.cases.update_one({"id": "c-src"}, {"$set": {"publicationStatus": "private"}})
    _assert_refused_accept(database, case, thread, artifact, auth)
    database.cases.update_one(
        {"id": "c-src"},
        {"$set": {"publicationStatus": "public", "publishedVersionId": "cv-missing"}},
    )
    _assert_refused_accept(database, case, thread, artifact, auth)
    database.cases.update_one({"id": "c-src"}, {"$set": {"publishedVersionId": "cv-1"}})
    _assert_accepted(database, case, thread, artifact, auth)


def _assert_refused_accept(database, case, thread, artifact, auth) -> None:
    denied = _refused_accept(database, case, thread, artifact, auth)
    assert denied.value.status_code == 409
    assert database.agent_artifacts.find_one({"id": artifact.id})["status"] == "pending"


def _assert_accepted(database, case, thread, artifact, auth) -> None:
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert result["artifact"].status == "accepted"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 2


def test_accept_rechecks_knowledge_and_material_sources(client: TestClient) -> None:
    auth = _login(client)
    database = client.app.state.database
    _seed_knowledge(database)
    _seed_material(database)
    database, case, thread, artifact = _seed_evidence_case(
        client, auth, [KNOWLEDGE_SOURCE, MATERIAL_SOURCE]
    )
    database.knowledge_sources.update_one({"id": "kn-1"}, {"$set": {"status": "retired"}})
    _assert_refused_accept(database, case, thread, artifact, auth)
    database.knowledge_sources.update_one({"id": "kn-1"}, {"$set": {"status": "active"}})
    database.materials.update_one({"id": "m-1"}, {"$set": {"accessLevel": "private"}})
    _assert_refused_accept(database, case, thread, artifact, auth)
    database.materials.update_one({"id": "m-1"}, {"$set": {"accessLevel": "public"}})
    _assert_accepted(database, case, thread, artifact, auth)
