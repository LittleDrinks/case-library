from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import UTC, datetime

import pytest
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from starlette.testclient import TestClient

from app.modules.agent.repository import AgentRepository
from app.modules.cases.service import CaseError

from app.modules.agent.runtime import agent
from tests.test_annotation_agent import _csrf, _send, _thread_id
from tests.test_annotation_discussion import (
    create_annotation,
    create_case,
    document,
    login,
    paragraph_start,
    save_document,
)


def _proposal_model(replacement: str, anchor: tuple[int, int] | None = None) -> FunctionModel:
    start, end = anchor or (paragraph_start(), paragraph_start() + 4)

    async def stream(messages, _info):
        start_index = max(
            index for index, message in enumerate(messages)
            if any(part.part_kind == "user-prompt" for part in getattr(message, "parts", []))
        )
        called = {
            part.tool_name
            for message in messages[start_index:]
            for part in getattr(message, "parts", [])
            if part.part_kind == "tool-call"
        }
        if "propose_revision" not in called:
            args = {"start": start, "end": end,
                    "replacement": replacement, "reason": "补充评价依据"}
            yield {0: DeltaToolCall(name="propose_revision", json_args=json.dumps(args))}
            return
        yield replacement

    return FunctionModel(stream_function=stream)


def _gated_model(gate: threading.Event, replacement: str) -> FunctionModel:
    """提议修订后挂起等待，制造完成事务之前的迟到窗口。"""

    async def stream(messages, _info):
        called = {
            part.tool_name
            for message in messages
            for part in getattr(message, "parts", [])
            if part.part_kind == "tool-call"
        }
        if "propose_revision" not in called:
            args = {"start": paragraph_start(), "end": paragraph_start() + 4,
                    "replacement": replacement, "reason": "补充评价依据"}
            yield {0: DeltaToolCall(name="propose_revision", json_args=json.dumps(args))}
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


def _revisions(client: TestClient, case: dict) -> list[dict]:
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    return row.get("revisions", [])


def test_second_round_after_unrelated_edit_appends_on_remapped_anchor(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    with agent.override(model=_proposal_model("第一轮改写")):
        first = _send(client, user, case, annotation, "第一轮")
    assert first.status_code == 200, first.text

    saved = save_document(
        client, user, case, document("前置目标正文"),
        [{"stepType": "replace", "from": paragraph_start(), "to": paragraph_start(),
          "slice": {"content": [{"type": "text", "text": "前置"}]}}],
    )
    assert saved.status_code == 200
    remapped = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert remapped["from"] == annotation["from"] + len("前置")
    assert [row["status"] for row in remapped["revisions"]] == ["pending"]

    with agent.override(model=_proposal_model("第二轮改写", (remapped["from"], remapped["to"]))):
        second = _send(client, user, saved.json(), remapped, "第二轮")
    assert second.status_code == 200, second.text
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert [revision["replacement"] for revision in row["revisions"]] == [
        "第一轮改写", "第二轮改写"
    ]
    assert all(revision["status"] == "pending" for revision in row["revisions"])
    assert row["revisions"][0]["target"]["from"] == remapped["from"]
    assert row["quote"] == annotation["quote"]
    assert all(revision["createdBy"] == annotation["createdBy"] for revision in row["revisions"])
    assert row["revisions"][0]["reason"] == "补充评价依据"
    assert row["revisions"][0]["target"]["quote"] == annotation["quote"]


def test_target_change_expires_revision_and_rejects_stale_new_round(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    with agent.override(model=_proposal_model("第一轮改写")):
        assert _send(client, user, case, annotation, "第一轮").status_code == 200

    changed = save_document(
        client, user, case, document("改写后的目标"),
        [{"stepType": "replace", "from": paragraph_start(),
          "to": paragraph_start() + len("目标正文"),
          "slice": {"content": [{"type": "text", "text": "改写后的目标"}]}}],
    )
    assert changed.status_code == 200
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert row["anchorState"] == "changed"
    assert [revision["status"] for revision in row["revisions"]] == ["expired"]

    stale = client.post(
        f"/api/cases/{case['id']}/agent/thread/{_thread_id(client, case['id'])}/stream",
        headers=_csrf(user),
        json={"id": "message-stale", "trigger": "submit-message", "messages": [{
            "id": "user-stale", "role": "user",
            "parts": [
                {"type": "text", "text": "基于旧文第二轮"},
                {"type": "data-selection", "data": {"from": paragraph_start(),
                                                    "to": paragraph_start() + len("目标正文")}},
                {"type": "data-annotation", "data": {"id": annotation["id"]}},
            ],
        }]},
    )
    assert stale.status_code == 409, stale.text
    after = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert [revision["replacement"] for revision in after["revisions"]] == ["第一轮改写"]
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == changed.json()["revision"]


def test_cancel_mid_run_leaves_no_revision_and_artifact(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    gate = threading.Event()
    worker = _send_in_thread(client, user, case, annotation, "第一轮", _gated_model(gate, "取消改写"))
    try:
        _wait_active(client, case["id"])
        thread_id = _thread_id(client, case["id"])
        cancelled = client.post(
            f"/api/cases/{case['id']}/agent/thread/{thread_id}/cancel", headers=_csrf(user),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelling"
    finally:
        gate.set()
        worker.join(30)
    assert not worker.is_alive()
    assert _revisions(client, case) == []
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["artifacts"] == []
    assert snapshot["latestRun"]["status"] == "cancelled"
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == case["revision"]


def test_busy_thread_rejects_second_annotation_send(client: TestClient) -> None:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    first_annotation = create_annotation(client, user, case, "目标正文")
    second_annotation = create_annotation(client, user, case, "目标正文")
    gate = threading.Event()
    worker = _send_in_thread(
        client, user, case, first_annotation, "第一轮", _gated_model(gate, "第一轮改写"),
    )
    try:
        _wait_active(client, case["id"])
        cross = _send(client, user, case, second_annotation, "抢跑第二轮")
        assert cross.status_code == 409, cross.text
    finally:
        gate.set()
        worker.join(30)
    assert not worker.is_alive()
    assert [revision["replacement"] for revision in _revisions(client, case)] == ["第一轮改写"]
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert [artifact["annotationId"] for artifact in snapshot["artifacts"]] == [first_annotation["id"]]


def test_late_completion_after_direct_close_marks_run_failed(client: TestClient) -> None:
    """mongomock 无事务：artifact 残留不在此断言，回滚语义由独立真 Mongo 验证。"""
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    gate = threading.Event()
    worker = _send_in_thread(client, user, case, annotation, "第一轮", _gated_model(gate, "迟到改写"))
    try:
        _wait_active(client, case["id"])
        closed = client.patch(
            f"/api/cases/{case['id']}/annotations/{annotation['id']}/status",
            headers=_csrf(user), json={"status": "resolved"},
        )
        assert closed.status_code == 200
    finally:
        gate.set()
        worker.join(30)
    assert not worker.is_alive()
    row = client.get(f"/api/cases/{case['id']}/annotations").json()[0]
    assert row["status"] == "resolved"
    assert row.get("revisions", []) == []
    snapshot = client.get(f"/api/cases/{case['id']}/agent/thread").json()
    assert snapshot["latestRun"]["status"] == "failed"
    assert client.get(f"/api/cases/{case['id']}").json()["revision"] == case["revision"]

@pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
def test_late_completion_rolls_back_on_real_replica_set():
    """真 Mongo 事务下迟到完成必须整体回滚；mongomock 无法表达该语义。"""
    import uuid

    from pymongo import MongoClient

    from app.modules.agent.models import AgentArtifact, AgentMessage, ArtifactTarget
    from app.modules.annotations import service as annotations

    mongo = MongoClient(os.environ["AUTH_QUERY_MONGODB_URI"])
    database = mongo.get_default_database()
    marker = uuid.uuid4().hex
    try:
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
        database.agent_threads.insert_one({
            "id": f"t-{marker}", "caseId": marker, "ownerId": "u1", "isDefault": True,
            "nextMessageSeq": 0, "eventSeq": 0, "activeRunId": f"r-{marker}",
            "lastRunId": None,
        })
        database.agent_runs.insert_one({
            "id": f"r-{marker}", "threadId": f"t-{marker}", "userId": "u1",
            "userMessageId": "m", "assistantMessageId": "am", "status": "active",
            "skillBindings": [], "readOnly": False, "writeAuthorized": True,
            "baseRevision": 1, "annotationId": f"an-{marker}", "resources": [],
            "toolTimings": {}, "startedAt": datetime.now(UTC),
        })
        annotations.change_status(database, marker, f"an-{marker}", "resolved", {"id": "u1", "role": "user"})
        artifact = AgentArtifact(
            id=f"a-{marker}", caseId=marker, threadId=f"t-{marker}", runId=f"r-{marker}",
            baseRevision=1,
            target=ArtifactTarget(**{"from": 1, "to": 7, "quote": "目标正文段落"}),
            annotationId=f"an-{marker}", replacement="迟到改写", reason="理由",
            createdAt=datetime.now(UTC),
        )
        message = AgentMessage(id="am", threadId=f"t-{marker}", runId=f"r-{marker}",
                               role="assistant", parts=[], createdAt=datetime.now(UTC))
        with pytest.raises(CaseError):
            AgentRepository(database).complete_run(f"r-{marker}", message, artifact=artifact)
        assert database.agent_artifacts.count_documents({"caseId": marker}) == 0
        assert database.agent_messages.count_documents({"threadId": f"t-{marker}"}) == 0
        row = database.annotations.find_one({"id": f"an-{marker}"})
        assert row["status"] == "resolved" and row.get("revisions", []) == []
    finally:
        mongo.close()
