"""#37 Artifact 安全：Run 锁定选区/基线、决定门禁、过期展示、证据复验与运行尾部可见性。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelRetry

from app.modules.agent import artifacts, prosemirror
from app.modules.agent.models import AgentMessage, ArtifactTarget, SourceRef
from app.modules.agent.repository import AgentRepository
from app.modules.agent.skills import propose_revision
from app.modules.cases.service import CaseError

PARAGRAPHS = ("第一段保持不变。", "第二段需要修订。")
REPLACEMENT = "第二段已按来源修订。"
RICH_DOCUMENT = {
    "type": "doc", "content": [
        {"type": "paragraph", "content": [
            {"type": "text", "text": "保留", "marks": [{"type": "bold"}]},
            {"type": "hardBreak"},
            {"type": "text", "text": "目标后", "marks": [{"type": "italic"}]},
        ]},
        {"type": "bulletList", "content": [{"type": "listItem", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "列表"}]},
        ]}]},
        {"type": "blockquote", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "引用"}]},
        ]},
    ],
}


# Native Tiptap/ProseMirror positions for these two paragraphs are 1..9 and 11..19.
FIRST = ArtifactTarget(from_pos=1, to_pos=9, quote=PARAGRAPHS[0])
SECOND = ArtifactTarget(from_pos=11, to_pos=19, quote=PARAGRAPHS[1])
SELECTION = {"type": "data-selection", "data": {"from": 11, "to": 19}}


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


def _create_case(client: TestClient, auth: dict, document: dict | None = None) -> dict:
    body = {"title": "锁目标案例", "document": document or _document(*PARAGRAPHS)}
    response = client.post("/api/cases", headers=_csrf(auth), json=body)
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
    return response


def _run_row(database, case_id: str) -> dict:
    thread_id = database.agent_threads.find_one({"caseId": case_id})["id"]
    row = database.agent_runs.find_one(
        {"threadId": thread_id}, {"_id": 0}, sort=[("startedAt", -1)]
    )
    return row


# ---- Run 创建即锁定 baseRevision；仅非空选区锁定目标范围 ----


def test_run_locks_selected_range_with_server_quote(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    response = _send(client, auth, case["id"], [
        {"type": "text", "text": "请修订选中的段落"}, SELECTION,
    ])
    assert response.status_code == 200, response.text
    run = _run_row(client.app.state.database, case["id"])
    assert run["baseRevision"] == 1
    assert run["target"] == {"from": SECOND.from_pos, "to": SECOND.to_pos,
                             "quote": PARAGRAPHS[1]}


def test_empty_or_cross_block_selection_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    first_from = FIRST.from_pos
    second_from = SECOND.from_pos
    for data in ({"from": second_from, "to": second_from},
                 {"from": first_from + 1, "to": second_from + 1}):
        response = _send(client, auth, case["id"], [
            {"type": "text", "text": "请修订"},
            {"type": "data-selection", "data": data},
        ])
        assert response.status_code == 422
    assert client.app.state.database.agent_runs.count_documents({}) == 0


def test_without_selection_no_target_is_locked(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth, _document("唯一段落。"))
    response = _send(client, auth, case["id"], [{"type": "text", "text": "请修订"}])
    assert response.status_code == 200, response.text
    run = _run_row(client.app.state.database, case["id"])
    assert run["baseRevision"] == 1
    assert run.get("target") is None


def test_selection_inside_list_and_quote_blocks_locks(client: TestClient) -> None:
    document = {"type": "doc", "content": [
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "列表要点。"}]},
            ]},
        ]},
        {"type": "blockquote", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "引用原文。"}]},
        ]},
    ]}
    auth = _login(client)
    blocks = prosemirror.text_blocks(document)
    for block in blocks:
        _assert_block_locks(client, auth, document, block)


def _assert_block_locks(client: TestClient, auth: dict, document: dict, block: dict) -> None:
    case = _create_case(client, auth, document)
    selection = {"type": "data-selection", "data": {
        "from": block["start"], "to": block["end"],
    }}
    response = _send(client, auth, case["id"], [
        {"type": "text", "text": "请修订"}, selection,
    ])
    assert response.status_code == 200, response.text
    quote = prosemirror.text_between(document, block["start"], block["end"])
    assert _run_row(client.app.state.database, case["id"])["target"] == {
        "from": block["start"], "to": block["end"], "quote": quote,
    }


# ---- 提议必须命中锁；工具期只暂存不落库 ----


def _locked_run(client: TestClient, auth: dict, case: dict, target: ArtifactTarget):
    """直接构造锁定 Run（保持 active，供各场景自行推进终态）。"""
    database = client.app.state.database
    repository = AgentRepository(database)
    thread = repository.default_thread(case["id"], auth["user"]["id"])
    run = repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "修订"}], {},
        "assistant-lock", base_revision=case["revision"], target=target,
    )
    return database, repository, thread, run


def _propose(database, case: dict, run, target: ArtifactTarget = SECOND,
             sources=(), replacement: str = REPLACEMENT):
    return artifacts.propose_artifact(
        database, case["id"], run.thread_id, run.id,
        target.from_pos, target.to_pos,
        replacement, "依据来源", list(sources), _owner(database, case),
    )


def _owner(database, case: dict) -> dict:
    row = database.cases.find_one({"id": case["id"]}, {"ownerId": 1})
    return {"id": row["ownerId"], "role": "user"}


def _publish(database, repository, run, artifact=None) -> None:
    """运行完成事务：助手消息、tool.result 与修订候选同时对外可见。"""
    message = AgentMessage(
        id=f"assistant-{run.id}", thread_id=run.thread_id, run_id=run.id,
        role="assistant", parts=[{"type": "text", "text": "完成"}],
        created_at=datetime.now(UTC),
    )
    assert repository.complete_run(
        run.id, message, resources=[], artifact=artifact,
    ) is True


def _save_prefix(client: TestClient, auth: dict, case: dict) -> dict:
    document = _document(f"前置{PARAGRAPHS[0]}", PARAGRAPHS[1])
    return client.patch(
        f"/api/cases/{case['id']}", headers=_csrf(auth), json={
            "revision": case["revision"], "document": document,
            "steps": [{"stepType": "replace", "from": 1, "to": 1,
                        "slice": {"content": [{"type": "text", "text": "前置"}]} }],
        },
    )


def test_propose_without_locked_target_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, _repository, _thread, run = _locked_run(client, auth, case, SECOND)
    database.agent_runs.update_one({"id": run.id}, {"$set": {"target": None}})
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run)
    assert excinfo.value.status_code == 422
    assert database.agent_artifacts.count_documents({}) == 0


def test_propose_off_locked_range_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, _repository, _thread, run = _locked_run(client, auth, case, SECOND)
    first = FIRST
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run, target=first)
    assert excinfo.value.status_code == 422
    assert database.agent_artifacts.count_documents({}) == 0


def test_propose_after_baseline_revision_change_is_refused(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, _repository, _thread, run = _locked_run(client, auth, case, SECOND)
    database.cases.update_one({"id": case["id"]}, {"$set": {"revision": 2}})
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run)
    assert excinfo.value.status_code == 409
    assert database.agent_artifacts.count_documents({}) == 0


def test_second_proposal_in_same_run_is_refused() -> None:
    ctx = SimpleNamespace(deps=SimpleNamespace(proposed=object()))
    with pytest.raises(ModelRetry):
        asyncio.run(propose_revision(ctx, SECOND.from_pos, SECOND.to_pos, "文本"))


def test_proposal_publishes_only_with_completed_run(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, repository, thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run)
    assert database.agent_artifacts.count_documents({}) == 0
    assert database.agent_thread_events.count_documents(
        {"type": "artifact.created"}
    ) == 0
    _publish(database, repository, run, artifact)
    row = database.agent_artifacts.find_one({"id": artifact.id}, {"_id": 0})
    assert row["status"] == "pending"
    assert row["target"] == {"from": SECOND.from_pos, "to": SECOND.to_pos,
                             "quote": PARAGRAPHS[1]}
    types = [event["type"] for event in
             database.agent_thread_events.find({"threadId": thread.id})]
    assert types == ["message.created", "run.started", "message.created",
                     "artifact.created", "run.completed"]


def test_cancelled_run_leaves_no_artifact(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, repository, thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run)
    assert repository.cancel_run(run.id) is True
    assert database.agent_artifacts.count_documents({}) == 0
    assert database.agent_thread_events.count_documents(
        {"type": "artifact.created"}
    ) == 0
    with pytest.raises(CaseError) as excinfo:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
        )
    assert excinfo.value.status_code == 404
    assert database.cases.find_one({"id": case["id"]})["revision"] == 1


def test_only_one_proposal_per_run(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, repository, _thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run)
    assert artifact.status == "pending"
    _publish(database, repository, run, artifact)
    with pytest.raises(CaseError) as excinfo:
        _propose(database, case, run)
    assert excinfo.value.status_code == 409
    assert database.agent_artifacts.count_documents({"runId": run.id}) == 1


# ---- 决定门禁、幂等、相反决定 ----


def test_repeat_same_decision_replays_opposite_conflicts(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, repository, thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run)
    _publish(database, repository, run, artifact)
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


# ---- 选区范围替换：子串生效且保留未选内容与标记 ----


def test_accept_replaces_only_selected_range(client: TestClient) -> None:
    document = {"type": "doc", "content": [{
        "type": "paragraph",
        "content": [
            {"type": "text", "text": "保留前缀。"},
            {"type": "text", "text": "旧目标文本", "marks": [{"type": "bold"}]},
            {"type": "text", "text": "保留后缀。", "marks": [{"type": "bold"}]},
        ],
    }]}
    auth = _login(client)
    case = _create_case(client, auth, document)
    block = prosemirror.text_blocks(document)[0]
    target = ArtifactTarget(from_pos=block["start"] + 5, to_pos=block["start"] + 10,
                            quote="旧目标文本")
    database, repository, thread, run = _locked_run(client, auth, case, target)
    artifact = _propose(database, case, run, target=target, replacement="已按来源修订。")
    _publish(database, repository, run, artifact)
    _assert_range_accepted(database, case, thread, artifact, auth)


def test_accept_maps_pending_artifact_after_unrelated_save(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, repository, thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run)
    _publish(database, repository, run, artifact)
    saved = _save_prefix(client, auth, case)
    assert saved.status_code == 200, saved.text
    row = database.agent_artifacts.find_one({"id": artifact.id})
    assert row["baseRevision"] == 2
    assert row["target"] == {"from": 13, "to": 21, "quote": PARAGRAPHS[1]}
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert result["artifact"].status == "accepted"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 3


def _assert_range_accepted(database, case, thread, artifact, auth) -> None:
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert result["artifact"].status == "accepted"
    updated = database.cases.find_one({"id": case["id"]})["document"]
    content = updated["content"][0]["content"]
    assert "".join(node["text"] for node in content) == "保留前缀。已按来源修订。保留后缀。"
    assert "marks" not in content[0] and content[-1]["marks"] == [{"type": "bold"}]


def test_utf16_selection_preserves_following_text() -> None:
    document = _document("A😀B")
    updated = prosemirror.replaced_document(document, 2, 4, "😀", "X")
    assert updated["content"][0]["content"][0]["text"] == "AXB"


def test_native_transform_preserves_rich_nodes() -> None:
    block = prosemirror.text_blocks(RICH_DOCUMENT)[0]
    updated = prosemirror.replaced_document(
        RICH_DOCUMENT, block["start"] + 3, block["end"] - 1, "目标", "新"
    )
    content = updated["content"]
    assert content[0]["content"][0]["marks"] == [{"type": "bold"}]
    assert content[0]["content"][1]["type"] == "hardBreak"
    assert content[0]["content"][-2] == {"type": "text", "text": "新"}
    assert content[0]["content"][-1] == {
        "type": "text", "text": "后", "marks": [{"type": "italic"}],
    }
    assert [node["type"] for node in content[1:]] == ["bulletList", "blockquote"]
    assert block == {"start": 1, "end": 7}


# ---- 基线过期：读取侧展示 expired，接受被拒 ----


def test_revision_change_marks_expired_and_blocks_accept(client: TestClient) -> None:
    auth = _login(client)
    case = _create_case(client, auth)
    database, repository, thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run)
    _publish(database, repository, run, artifact)
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
    case = _create_case(client, auth)
    database, repository, thread, run = _locked_run(client, auth, case, SECOND)
    artifact = _propose(database, case, run, sources=sources)
    _publish(database, repository, run, artifact)
    return database, case, thread, artifact


def _assert_refused_accept(database, case, thread, artifact, auth) -> None:
    with pytest.raises(CaseError) as denied:
        artifacts.decide_artifact(
            database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
        )
    assert denied.value.status_code == 409
    assert database.agent_artifacts.find_one({"id": artifact.id})["status"] == "pending"


def _assert_accepted(database, case, thread, artifact, auth) -> None:
    result = artifacts.decide_artifact(
        database, case["id"], thread.id, artifact.id, auth["user"], "accepted",
    )
    assert result["artifact"].status == "accepted"
    assert database.cases.find_one({"id": case["id"]})["revision"] == 2


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
