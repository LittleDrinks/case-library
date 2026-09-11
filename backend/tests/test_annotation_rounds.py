from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import UTC, datetime

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from starlette.testclient import TestClient

from app.modules.agent.repository import AgentRepository
from app.modules.agent.runtime import agent
from app.modules.cases.service import CaseError
from tests.test_annotation_agent import _csrf, _send, _thread_id
from tests.test_annotation_discussion import (
    _linked_artifact,
    create_annotation,
    create_case,
    document,
    login,
    paragraph_start,
    save_document,
)

PROPOSAL_ARGS = {"start": paragraph_start(), "end": paragraph_start() + 4}


def _last_user_calls(messages) -> set[str]:
    start = max(
        (index for index, message in enumerate(messages)
         if any(part.part_kind == "user-prompt" for part in getattr(message, "parts", []))),
        default=0,
    )
    return {
        part.tool_name
        for message in messages[start:]
        for part in getattr(message, "parts", [])
        if part.part_kind == "tool-call"
    }


def _propose_call(start: int, end: int, replacement: str) -> dict:
    return {0: DeltaToolCall(name="propose_revision", json_args=json.dumps(
        {"start": start, "end": end, "replacement": replacement, "reason": "补充评价依据"},
    ))}


def _proposal_model(replacement: str, anchor: tuple[int, int] | None = None) -> FunctionModel:
    start, end = anchor or (PROPOSAL_ARGS["start"], PROPOSAL_ARGS["end"])

    async def stream(messages, _info):
        if "propose_revision" not in _last_user_calls(messages):
            yield _propose_call(start, end, replacement)
            return
        yield replacement

    return FunctionModel(stream_function=stream)


def _gated_model(gate: threading.Event, replacement: str) -> FunctionModel:
    """提议修订后挂起等待，制造完成事务之前的迟到窗口。"""

    async def stream(messages, _info):
        if "propose_revision" not in _last_user_calls(messages):
            yield _propose_call(PROPOSAL_ARGS["start"], PROPOSAL_ARGS["end"], replacement)
            return
        while not gate.is_set():
            await asyncio.sleep(0.02)
        yield replacement

    return FunctionModel(stream_function=stream)


def _send_in_thread(client: TestClient, user: dict, case: dict, annotation: dict, text: str,
                    model: FunctionModel):
    def target():
        with agent.override(model=model):
            _send(client, user, case, annotation, text)

    worker = threading.Thread(target=_worker_guard(target))
    worker.start()
    return worker


def _worker_guard(target):
    def safe():
        try:
            target()
        except Exception as error:  # pragma: no cover - 线程内异常带到断言更难排查
            print(f"stream worker error: {error!r}")

    return safe


def _wait_active(client: TestClient, case_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/cases/{case_id}/agent/thread").json()
        if snapshot.get("activeRun"):
            return snapshot
        time.sleep(0.05)
    raise AssertionError("run did not become active")


def _start_annotation_run(client: TestClient, user: dict, case: dict, annotation: dict,
                          replacement: str):
    gate = threading.Event()
    worker = _send_in_thread(
        client, user, case, annotation, "第一轮", _gated_model(gate, replacement),
    )
    _wait_active(client, case["id"])
    return gate, worker


def _release(gate: threading.Event, worker: threading.Thread) -> None:
    gate.set()
    worker.join(30)
    assert not worker.is_alive()


def _annotation_row(client: TestClient, case: dict) -> dict:
    return client.get(f"/api/cases/{case['id']}/annotations").json()[0]


def _replacements(row: dict) -> list[str]:
    return [revision["replacement"] for revision in row["revisions"]]


def _run_round(client: TestClient, user: dict, case: dict, annotation: dict, text: str,
               replacement: str, anchor: tuple[int, int] | None = None) -> None:
    with agent.override(model=_proposal_model(replacement, anchor)):
        response = _send(client, user, case, annotation, text)
    assert response.status_code == 200, response.text


def _prepend_unrelated_paragraph(client: TestClient, user: dict, case: dict) -> dict:
    saved = save_document(
        client, user, case, document("前置目标正文"),
        [{"stepType": "replace", "from": paragraph_start(), "to": paragraph_start(),
          "slice": {"content": [{"type": "text", "text": "前置"}]}}],
    )
    assert saved.status_code == 200
    return saved.json()


def _assert_round_history(row: dict, annotation: dict) -> None:
    assert _replacements(row) == ["第一轮改写", "第二轮改写"]
    assert all(revision["status"] == "pending" for revision in row["revisions"])
    assert row["revisions"][0]["target"]["from"] == row["from"]
    assert row["quote"] == annotation["quote"]
    assert all(revision["createdBy"] == annotation["createdBy"] for revision in row["revisions"])
    assert row["revisions"][0]["reason"] == "补充评价依据"
    assert row["revisions"][0]["target"]["quote"] == annotation["quote"]


def test_second_round_after_unrelated_edit_appends_on_remapped_anchor(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    _run_round(client, user, case, annotation, "第一轮", "第一轮改写")

    saved = _prepend_unrelated_paragraph(client, user, case)
    remapped = _annotation_row(client, case)
    assert remapped["from"] == annotation["from"] + len("前置")
    assert [row["status"] for row in remapped["revisions"]] == ["pending"]

    anchor = (remapped["from"], remapped["to"])
    _run_round(client, user, saved, remapped, "第二轮", "第二轮改写", anchor)
    _assert_round_history(_annotation_row(client, case), annotation)


def _rewrite_target_paragraph(client: TestClient, user: dict, case: dict) -> dict:
    changed = save_document(
        client, user, case, document("改写后的目标"),
        [{"stepType": "replace", "from": paragraph_start(),
          "to": paragraph_start() + len("目标正文"),
          "slice": {"content": [{"type": "text", "text": "改写后的目标"}]}}],
    )
    assert changed.status_code == 200
    return changed.json()


def _stale_stream(client: TestClient, user: dict, case: dict, annotation: dict):
    selection = {"from": paragraph_start(), "to": paragraph_start() + len("目标正文")}
    return client.post(
        f"/api/cases/{case['id']}/agent/thread/{_thread_id(client, case['id'])}/stream",
        headers=_csrf(user),
        json={"id": "message-stale", "trigger": "submit-message", "messages": [{
            "id": "user-stale", "role": "user",
            "parts": [
                {"type": "text", "text": "基于旧文第二轮"},
                {"type": "data-selection", "data": selection},
                {"type": "data-annotation", "data": {"id": annotation["id"]}},
            ],
        }]},
    )


def test_target_change_expires_revision_and_rejects_stale_new_round(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    _run_round(client, user, case, annotation, "第一轮", "第一轮改写")

    changed = _rewrite_target_paragraph(client, user, case)
    row = _annotation_row(client, case)
    assert row["anchorState"] == "changed"
    assert [revision["status"] for revision in row["revisions"]] == ["expired"]

    assert _stale_stream(client, user, changed, row).status_code == 409
    after = _annotation_row(client, case)
    assert _replacements(after) == ["第一轮改写"]
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == changed["revision"]


def test_cancel_mid_run_leaves_no_revision_and_artifact(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    gate, worker = _start_annotation_run(client, user, case, annotation, "取消改写")
    try:
        thread_id = _thread_id(client, case["id"])
        cancelled = client.post(
            f"/api/cases/{case['id']}/agent/thread/{thread_id}/cancel", headers=_csrf(user),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelling"
    finally:
        _release(gate, worker)
    assert _annotation_row(client, case).get("revisions", []) == []
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["artifacts"] == []
    assert snapshot["latestRun"]["status"] == "cancelled"
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == case["revision"]


def test_busy_thread_rejects_second_annotation_send(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    first = create_annotation(client, user, case, "目标正文")
    second = create_annotation(client, user, case, "目标正文")
    gate, worker = _start_annotation_run(client, user, case, first, "第一轮改写")
    try:
        cross = _send(client, user, case, second, "抢跑第二轮")
        assert cross.status_code == 409, cross.text
    finally:
        _release(gate, worker)
    assert _replacements(_annotation_row(client, case)) == ["第一轮改写"]
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert [artifact["annotationId"] for artifact in snapshot["artifacts"]] == [first["id"]]


def test_late_completion_after_direct_close_marks_run_failed(client: TestClient) -> None:
    """mongomock 无事务：artifact 残留不在此断言，回滚语义由真副本集测试锁定。"""
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    gate, worker = _start_annotation_run(client, user, case, annotation, "迟到改写")
    try:
        closed = client.patch(
            f"/api/cases/{case['id']}/annotations/{annotation['id']}/status",
            headers=_csrf(user), json={"status": "resolved"},
        )
        assert closed.status_code == 200
    finally:
        _release(gate, worker)
    row = _annotation_row(client, case)
    assert row["status"] == "resolved" and row.get("revisions", []) == []
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["latestRun"]["status"] == "failed"
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == case["revision"]


def _seed_late_annotation_run(database, marker: str) -> None:
    _seed_real_annotation(database, marker)
    _seed_real_run(database, marker)


def _seed_real_annotation(database, marker: str) -> None:
    database.cases.insert_one({
        "id": marker, "ownerId": "u1", "revision": 1, "title": marker,
        "workflowStatus": "draft",
        "document": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "目标正文段落"}]},
        ]},
    })
    database.annotations.insert_one({
        "id": f"an-{marker}", "caseId": marker, "versionId": None,
        "quote": "目标正文段落", "section": "p", "content": "意见", "source": "manual",
        "from": 1, "to": 7, "quoteHash": "h", "revision": 1,
        "status": "pending", "anchorState": "active", "replies": [],
        "createdBy": "u1",
    })


def _seed_real_run(database, marker: str) -> None:
    database.agent_threads.insert_one({
        "id": f"t-{marker}", "caseId": marker, "ownerId": "u1", "isDefault": True,
        "nextMessageSeq": 0, "eventSeq": 0, "activeRunId": f"r-{marker}", "lastRunId": None,
    })
    database.agent_runs.insert_one({
        "id": f"r-{marker}", "threadId": f"t-{marker}", "userId": "u1",
        "userMessageId": "m", "assistantMessageId": "am", "status": "active",
        "skillBindings": [], "readOnly": False, "writeAuthorized": True,
        "baseRevision": 1, "annotationId": f"an-{marker}", "resources": [],
        "toolTimings": {}, "startedAt": datetime.now(UTC),
    })


def _late_artifact(marker: str, base_revision: int = 1):
    from app.modules.agent.models import AgentArtifact, ArtifactTarget

    return AgentArtifact(
        id=f"a-{marker}", caseId=marker, threadId=f"t-{marker}", runId=f"r-{marker}",
        baseRevision=base_revision,
        target=ArtifactTarget(**{"from": 1, "to": 7, "quote": "目标正文段落"}),
        annotationId=f"an-{marker}", replacement="迟到改写", reason="理由",
        createdAt=datetime.now(UTC),
    )


def _late_message(marker: str):
    from app.modules.agent.models import AgentMessage

    return AgentMessage(id="am", threadId=f"t-{marker}", runId=f"r-{marker}",
                        role="assistant", parts=[], createdAt=datetime.now(UTC))


def _close_annotation(database, marker: str) -> None:
    from app.modules.annotations import service as annotations

    annotations.change_status(database, marker, f"an-{marker}", "resolved",
                              {"id": "u1", "role": "user"})


def _assert_rolled_back(database, marker: str) -> None:
    assert database.agent_artifacts.count_documents({"caseId": marker}) == 0
    assert database.agent_messages.count_documents({"threadId": f"t-{marker}"}) == 0
    row = database.annotations.find_one({"id": f"an-{marker}"})
    assert row["status"] == "resolved" and row.get("revisions", []) == []


def _merge_target() -> dict:
    return {"from": 1, "to": 7, "quote": "目标正文段落"}


def _merge_artifact(marker: str, index: int, replacement: str) -> dict:
    return {
        "id": f"artifact-{marker}-{index}", "caseId": marker,
        "threadId": f"thread-{marker}", "runId": f"run-{marker}-{index}",
        "status": "pending", "baseRevision": 1, "target": _merge_target(),
        "annotationId": f"an-{marker}", "replacement": replacement,
        "reason": "理由", "sources": [], "createdAt": datetime.now(UTC),
    }


def _merge_revision(marker: str, index: int, replacement: str) -> dict:
    return {
        "id": f"arv-{marker}-{index}", "artifactId": f"artifact-{marker}-{index}",
        "runId": f"run-{marker}-{index}", "baseRevision": 1,
        "target": _merge_target(), "replacement": replacement, "reason": "理由",
        "status": "pending", "createdBy": "u1", "createdAt": datetime.now(UTC),
    }

def _pending_artifact_row(client, annotation, base_revision, replacement, suffix):
    database = client.app.state.database
    artifact = _linked_artifact(
        annotation, f"thread-{annotation['id']}", f"run-{suffix}",
        f"artifact-{suffix}", replacement,
    ) | {"baseRevision": base_revision}
    database.agent_artifacts.insert_one(artifact)
    return artifact


def _append_revision_in_expiry_window(client, monkeypatch, annotation, artifact):
    """拒绝事务重读前经真实 record_ai_revision 追加候选，复刻并发落库时序。"""
    from app.modules.agent.models import AgentArtifact, ArtifactTarget
    from app.modules.annotations import service as annotations

    original = annotations._expire_invalid_revisions

    def save_concurrent(database, _case_id, _annotation_id, _user, session):
        current = database.annotations.find_one({"id": annotation["id"]})
        target = ArtifactTarget(**{"from": current["from"], "to": current["to"],
                                   "quote": current["quote"]})
        clean = {key: value for key, value in artifact.items() if key != "_id"}
        row = AgentArtifact.model_validate({**clean, "target": target})
        annotations.record_ai_revision(database, row, annotation["createdBy"], session)
        return original(database, _case_id, _annotation_id, _user, session)

    monkeypatch.setattr(annotations, "_expire_invalid_revisions", save_concurrent)


def _assert_rejection_preserves_concurrent(client, annotation, artifact, stale):
    """拒绝后：并发候选 pending 保留，确实失效的旧候选精确过期。"""
    database = client.app.state.database
    row = database.annotations.find_one({"id": annotation["id"]})
    assert [revision["replacement"] for revision in row["revisions"]] == [
        "过期基线改写", "并发新增改写",
    ]
    assert [revision["status"] for revision in row["revisions"]] == ["expired", "pending"]
    assert database.agent_artifacts.find_one({"id": artifact["id"]})["status"] == "pending"
    assert database.agent_artifacts.find_one({"id": stale})["status"] == "expired"


def _assert_surviving_candidate_adoptable(client, user, annotation):
    """拒绝后存活的有效候选仍可采用：正文与关闭状态原子一致。"""
    database = client.app.state.database
    adopted = client.post(
        f"/api/cases/{annotation['caseId']}/annotations/{annotation['id']}/merge",
        headers=_csrf(user),
    )
    assert adopted.status_code == 200
    result = adopted.json()
    assert result["annotation"]["status"] == "resolved"
    assert [revision["status"] for revision in result["annotation"]["revisions"]] == [
        "expired", "accepted",
    ]
    assert "并发新增改写" in result["case"]["document"]["content"][-1]["content"][0]["text"]
    final = database.annotations.find_one({"id": annotation["id"]})
    assert [revision["status"] for revision in final["revisions"]] == ["expired", "accepted"]


def test_rejected_merge_keeps_concurrent_new_revision_pending(client, monkeypatch) -> None:
    """拒绝合并的过期事务重读库内状态：并发保存的候选保留，过时候选精确失效。"""
    from tests.test_annotation_discussion import merge_path, save_title, seed_linked_revisions

    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    stale = seed_linked_revisions(client, annotation, "过期基线改写")[0]
    changed = save_title(client, user, case, "标题已更新")
    assert changed.status_code == 200
    artifact = _pending_artifact_row(
        client, annotation, changed.json()["revision"], "并发新增改写", "concurrent",
    )
    _append_revision_in_expiry_window(client, monkeypatch, annotation, artifact)
    rejected = client.post(merge_path(changed.json(), annotation), headers=_csrf(user))
    assert rejected.status_code == 409
    _assert_rejection_preserves_concurrent(client, annotation, artifact, stale)
    _assert_surviving_candidate_adoptable(client, user, annotation)


def _revision_flow_annotation(client, user):
    """第一轮候选 + 标题保存推进修订号：构造锚点 active 且基线过期的场景。"""
    from tests.test_annotation_discussion import save_title

    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    _run_round(client, user, case, annotation, "第一轮", "第一轮改写")
    saved = save_title(client, user, case, "标题更新后的案例")
    assert saved.status_code == 200
    return case, annotation, saved


def _assert_mutation_views_expired(client, user, case, annotation, saved):
    """编辑与回复的响应视图按当前修订号判定候选失效。"""
    root = f"/api/cases/{case['id']}/annotations/{annotation['id']}"
    edited = client.patch(root, headers=_csrf(user), json={"content": "更新意见"})
    assert edited.status_code == 200
    assert [revision["status"] for revision in edited.json()["revisions"]] == ["expired"]
    replied = client.post(f"{root}/replies", headers=_csrf(user),
                          json={"content": "补充讨论"})
    assert replied.status_code == 200
    assert [revision["status"] for revision in replied.json()["revisions"]] == ["expired"]
    revision_now = client.get(f"/api/cases/{case['id']}").json()["revision"]
    assert revision_now == saved.json()["revision"]


def test_annotation_update_and_reply_show_current_revision_status(client: TestClient) -> None:
    """编辑与回复响应按当前案例修订判定候选有效性，不用可选版本校验显示 pending。"""
    user = login(client, "user", "user123")
    case, annotation, saved = _revision_flow_annotation(client, user)
    row = _annotation_row(client, case)
    assert row["anchorState"] == "active"
    assert [revision["status"] for revision in row["revisions"]] == ["expired"]
    _assert_mutation_views_expired(client, user, case, annotation, saved)


def _interleave_title_save(client, monkeypatch, user, case, content: str):
    """mutation 写入前触发一次真实标题保存，制造读取-写入窗口。"""
    from tests.test_annotation_discussion import save_title

    database = client.app.state.database
    original_find = database.annotations.find_one_and_update

    def save_then_update(filter, update, **kwargs):
        if update.get("$set", {}).get("content") == content:
            save_title(client, user, case, "窗口期并发标题")
        return original_find(filter, update, **kwargs)

    monkeypatch.setattr(
        database.annotations, "find_one_and_update", save_then_update,
    )


def test_mutation_response_matches_fresh_read_after_concurrent_title_save(client, monkeypatch) -> None:
    """mutation 读取案例后、写入前并发保存标题：响应状态必须与随后读取一致。"""
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    _run_round(client, user, case, annotation, "第一轮", "第一轮改写")
    _interleave_title_save(client, monkeypatch, user, case, "窗口期意见")
    root = f"/api/cases/{case['id']}/annotations/{annotation['id']}"
    edited = client.patch(root, headers=_csrf(user), json={"content": "窗口期意见"})
    assert edited.status_code == 200
    fresh = _annotation_row(client, {"id": case["id"]})
    assert [revision["status"] for revision in fresh["revisions"]] == ["expired"]
    assert [revision["status"] for revision in edited.json()["revisions"]] == [
        revision["status"] for revision in fresh["revisions"]
    ]


def _seed_merge_artifacts(database, marker: str) -> None:
    _seed_real_annotation(database, marker)
    database.agent_threads.insert_one({
        "id": f"thread-{marker}", "caseId": marker, "ownerId": "u1", "eventSeq": 0,
    })
    replacements = ("旧轮改写", "最新有效改写")
    for index, replacement in enumerate(replacements, 1):
        database.agent_runs.insert_one({
            "id": f"run-{marker}-{index}", "threadId": f"thread-{marker}",
            "status": "completed",
        })
        database.agent_artifacts.insert_one(_merge_artifact(marker, index, replacement))
    database.annotations.update_one(
        {"id": f"an-{marker}"},
        {"$set": {"revisions": [
            _merge_revision(marker, 1, replacements[0]),
            _merge_revision(marker, 2, replacements[1]),
        ]}},
    )


def _cleanup_merge_data(database, marker: str) -> None:
    database.case_snapshots.delete_many({"caseId": marker})
    database.agent_thread_events.delete_many({"threadId": f"thread-{marker}"})
    database.agent_artifacts.delete_many({"caseId": marker})
    database.agent_runs.delete_many({"id": {"$regex": f"^run-{marker}-"}})
    database.agent_threads.delete_many({"id": f"thread-{marker}"})
    database.annotations.delete_many({"caseId": marker})
    database.cases.delete_many({"id": marker})


def _open_merge_database():
    from pymongo import MongoClient

    mongo = MongoClient(os.environ["AUTH_QUERY_MONGODB_URI"])
    return mongo, mongo.get_default_database()


def _merge_once(database, marker: str):
    from app.modules.annotations import service as annotations

    return annotations.merge_annotation(
        database, marker, f"an-{marker}", {"id": "u1", "role": "user"}
    )


def _assert_merge_result(database, marker: str, result: dict) -> None:
    assert result["case"]["revision"] == 2
    assert result["annotation"]["status"] == "resolved"
    assert [row["status"] for row in result["annotation"]["revisions"]] == [
        "expired", "accepted",
    ]
    statuses = database.agent_artifacts.find(
        {"caseId": marker}, {"_id": 0, "status": 1}
    ).sort("id", 1)
    assert [row["status"] for row in statuses] == ["expired", "accepted"]


@pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
def test_merge_keeps_selected_artifact_accepted_on_real_replica_set():
    mongo, database = _open_merge_database()
    marker = f"annotation-merge-{uuid.uuid4().hex}"
    try:
        _seed_merge_artifacts(database, marker)
        _assert_merge_result(database, marker, _merge_once(database, marker))
    finally:
        _cleanup_merge_data(database, marker)
        mongo.close()


def _run_concurrent_merges(database, marker: str) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor

    request = (database, marker, f"an-{marker}", {"id": "u1", "role": "user"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_merge_once, *request[:2]) for _ in range(2)]
        return [future.result() for future in futures]

def _assert_single_commit(database, marker: str, outcomes: list[dict]) -> None:
    assert all(result["case"]["revision"] == 2 for result in outcomes)
    assert database.case_snapshots.count_documents(
        {"caseId": marker, "kind": "pre_annotation_merge"}
    ) == 1
    assert database.agent_artifacts.count_documents({"caseId": marker, "status": "accepted"}) == 1
    assert database.agent_artifacts.count_documents({"caseId": marker, "status": "expired"}) == 1


@pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
def test_concurrent_merge_commits_once_on_real_replica_set():
    mongo, database = _open_merge_database()
    marker = f"annotation-merge-concurrent-{uuid.uuid4().hex}"
    try:
        _seed_merge_artifacts(database, marker)
        outcomes = _run_concurrent_merges(database, marker)
        _assert_single_commit(database, marker, outcomes)
    finally:
        _cleanup_merge_data(database, marker)
        mongo.close()


@pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
def test_late_completion_rolls_back_on_real_replica_set():
    """真 Mongo 事务下迟到完成必须整体回滚；mongomock 无法表达该语义。"""
    from pymongo import MongoClient

    mongo = MongoClient(os.environ["AUTH_QUERY_MONGODB_URI"])
    database = mongo.get_default_database()
    marker = uuid.uuid4().hex
    try:
        _seed_late_annotation_run(database, marker)
        _close_annotation(database, marker)
        with pytest.raises(CaseError):
            AgentRepository(database).complete_run(
                f"r-{marker}", _late_message(marker), artifact=_late_artifact(marker),
            )
        _assert_rolled_back(database, marker)
    finally:
        mongo.close()


def _seed_stale_then_active_run(database, marker: str) -> None:
    """案例推进到 revision 2 且带失效旧候选；活跃 run 锚定新基线待真实落库。"""
    _seed_real_annotation(database, marker)
    _seed_real_run(database, marker)
    database.agent_runs.update_one(
        {"id": f"r-{marker}"}, {"$set": {"baseRevision": 2}},
    )
    database.cases.update_one({"id": marker}, {"$set": {"revision": 2}})
    stale = _merge_revision(marker, 1, "过期基线改写")
    stale["baseRevision"] = 1
    stale_artifact = {**_merge_artifact(marker, 1, "过期基线改写"),
                      "status": "expired", "baseRevision": 1}
    database.agent_artifacts.insert_one(stale_artifact)
    database.annotations.update_one(
        {"id": f"an-{marker}"}, {"$set": {"revisions": [stale]}},
    )


def _run_real_completion_in_thread(database, marker: str, committed):
    """独立线程执行真实 complete_run：事务内 record_ai_revision 落新候选。"""
    from app.modules.agent.models import AgentMessage
    from app.modules.agent.repository import AgentRepository

    def run_completion():
        assistant = AgentMessage(
            id="am", threadId=f"t-{marker}", runId=f"r-{marker}",
            role="assistant", parts=[], createdAt=datetime.now(UTC))
        artifact = _late_artifact(marker, base_revision=2)
        outcome = AgentRepository(database).complete_run(
            f"r-{marker}", assistant, artifact=artifact)
        assert outcome is True
        committed.set()

    worker = threading.Thread(target=run_completion)
    worker.start()
    worker.join(30)
    assert not worker.is_alive()


def _expire_after_completion_barrier(database, entered, committed):
    """过期事务入口先报到达，再等 completion 真实提交，构造真交错。"""
    from app.modules.annotations import service as annotations

    original = annotations._expire_invalid_revisions

    def expire_once_completed(database_arg, case_id, annotation_id, user_arg, session):
        entered.set()
        try:
            assert committed.wait(10), "completion 未在窗口内提交"
            return original(database_arg, case_id, annotation_id, user_arg, session)
        except BaseException as barrier_error:
            barrier_error._barrier_failure = True
            raise

    return original, expire_once_completed


def _assert_interleaved_survivor_adoptable(database, marker: str):
    """新候选保留 pending 且随后采用；正文、状态、Artifact 原子一致。"""
    row = database.annotations.find_one({"id": f"an-{marker}"})
    assert [revision["status"] for revision in row["revisions"]] == ["expired", "pending"]
    assert database.agent_artifacts.find_one({"id": f"a-{marker}"})["status"] == "pending"
    result = _merge_once(database, marker)
    assert result["annotation"]["status"] == "resolved"
    assert [revision["status"] for revision in result["annotation"]["revisions"]] == [
        "expired", "accepted",
    ]
    assert "迟到改写" in result["case"]["document"]["content"][-1]["content"][0]["text"]
    assert database.agent_artifacts.find_one({"id": f"a-{marker}"})["status"] == "accepted"


def _reject_merge_in_thread(database, marker: str):
    """后台线程执行 merge：应因无有效修订被拒（CaseError）。异常传播主线程。"""
    import pytest as _pytest

    worker_failure = []

    def run_merge():
        try:
            with _pytest.raises(CaseError):
                _merge_once(database, marker)
        except BaseException as error:
            worker_failure.append(error)

    worker = threading.Thread(target=run_merge)
    worker.start()
    return worker, worker_failure


def _wire_expiry_barrier(database, monkeypatch):
    """打过期事务屏障：返回 (marker, entered, committed)。"""
    from threading import Event

    from app.modules.annotations import service as annotations

    marker = f"annotation-merge-interleave-{uuid.uuid4().hex}"
    entered, committed = Event(), Event()
    original, barrier = _expire_after_completion_barrier(database, entered, committed)
    monkeypatch.setattr(annotations, "_expire_invalid_revisions", barrier)
    return marker, entered, committed



@pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
def test_rejected_merge_interleaves_real_completion_on_replica_set(monkeypatch):
    mongo, database = _open_merge_database()
    marker, entered, committed = _wire_expiry_barrier(database, monkeypatch)
    try:
        _seed_stale_then_active_run(database, marker)
        merge_worker, worker_failure = _reject_merge_in_thread(database, marker)
        assert entered.wait(10), "merge 未抵达过期事务入口"
        _run_real_completion_in_thread(database, marker, committed)
        merge_worker.join(30)
        assert not merge_worker.is_alive()
        if worker_failure:
            raise worker_failure[0]
        _assert_interleaved_survivor_adoptable(database, marker)
    finally:
        monkeypatch.undo()
        _cleanup_merge_data(database, marker)
        mongo.close()


