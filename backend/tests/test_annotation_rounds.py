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


def _failure_model() -> FunctionModel:
    async def stream(_messages, _info):
        raise RuntimeError("upstream unavailable")
        yield "unreachable"

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


def _await_run_status(client: TestClient, thread_id: str, status: str) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = client.app.state.database.agent_runs.find_one(
            {"threadId": thread_id, "status": status}, {"_id": 0}
        )
        if run:
            return run
        time.sleep(0.02)
    raise AssertionError(f"run did not become {status}")


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


def _retry_request(client: TestClient, user: dict, case: dict, message_id: str):
    return client.post(
        f"/api/cases/{case['id']}/agent/thread/{_thread_id(client, case['id'])}/stream",
        headers=_csrf(user),
        json={"id": "retry-message", "trigger": "regenerate-message",
          "messageId": message_id, "messages": []},
    )


def _failed_annotation_setup(client: TestClient) -> tuple[dict, dict, dict, str, dict]:
    user = login(client, "user", "user123")
    case = create_case(client, user, "目标正文")
    annotation = create_annotation(client, user, case, "目标正文")
    with agent.override(model=_failure_model()):
        initial = _send(client, user, case, annotation, "重试消息")
    assert initial.status_code == 200, initial.text
    thread_id = _thread_id(client, case["id"])
    failed = _await_run_status(client, thread_id, "failed")
    assert failed["status"] == "failed"
    assert failed["annotationId"] == annotation["id"]
    assert _annotation_row(client, case).get("revisions", []) == []
    user_message = client.app.state.database.agent_messages.find_one(
        {"id": failed["userMessageId"]}, {"_id": 0}
    )
    return user, case, annotation, thread_id, user_message


def test_retry_of_failed_annotation_run_keeps_annotation_binding(client: TestClient) -> None:
    user, case, annotation, thread_id, user_message = _failed_annotation_setup(client)

    with agent.override(model=_proposal_model("重试改写")):
        response = _retry_request(client, user, case, user_message["id"])
    assert response.status_code == 200, response.text

    retried = _await_run_status(client, thread_id, "completed")
    assert retried["status"] == "completed"
    assert retried["annotationId"] == annotation["id"]
    assert _replacements(_annotation_row(client, case)) == ["重试改写"]

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


def _late_artifact(marker: str) -> "AgentArtifact":
    from app.modules.agent.models import AgentArtifact, ArtifactTarget

    return AgentArtifact(
        id=f"a-{marker}", caseId=marker, threadId=f"t-{marker}", runId=f"r-{marker}",
        baseRevision=1,
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


@pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
def test_late_completion_rolls_back_on_real_replica_set():
    """真 Mongo 事务下迟到完成必须整体回滚；mongomock 无法表达该语义。"""
    from pymongo import MongoClient

    from app.modules.annotations import service as annotations

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
