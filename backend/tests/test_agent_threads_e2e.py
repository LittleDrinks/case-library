"""真实 MongoDB replica set 上的 Thread 证据：默认唯一索引并发与 per-Thread 事件顺序。"""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.agent.models import AgentMessage
from app.modules.agent.repository import AgentRepository

MONGO_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("AUTH_QUERY_MONGODB_URI")
EVENT_TYPES = ["message.created", "run.started", "message.created", "run.completed"]


def _repository() -> tuple[MongoClient, AgentRepository]:
    mongo = MongoClient(MONGO_URI)
    return mongo, AgentRepository(mongo.get_default_database())


def _scope() -> tuple[str, str]:
    return f"case-{uuid.uuid4().hex}", f"user-{uuid.uuid4().hex}"


def _raced_default_thread(repository, case_id: str, owner_id: str, barrier: Barrier) -> str:
    barrier.wait(timeout=10)
    return repository.default_thread(case_id, owner_id).id


def test_concurrent_default_creation_keeps_single_default_on_replica_set() -> None:
    mongo, repository = _repository()
    case_id, owner_id = _scope()
    barrier = Barrier(4)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(_raced_default_thread, repository, case_id, owner_id, barrier)
                for _ in range(4)
            ]
            ids = [future.result(timeout=15) for future in futures]
        assert len(set(ids)) == 1
        assert mongo.get_default_database().agent_threads.count_documents(
            {"caseId": case_id, "ownerId": owner_id, "isDefault": True}
        ) == 1
    finally:
        mongo.close()


def test_second_default_insert_is_rejected_by_unique_index() -> None:
    mongo, repository = _repository()
    case_id, owner_id = _scope()
    try:
        repository.default_thread(case_id, owner_id)
        duplicate = {
            "id": new_id("thread"), "caseId": case_id, "ownerId": owner_id,
            "isDefault": True, "nextMessageSeq": 0, "eventSeq": 0,
            "activeRunId": None, "lastRunId": None, "createdAt": datetime.now(UTC),
        }
        with pytest.raises(DuplicateKeyError):
            mongo.get_default_database().agent_threads.insert_one(duplicate)
    finally:
        mongo.close()


def _run_turn(repository, thread, owner_id: str) -> str:
    assistant_id = new_id("message")
    run = repository.start_run(
        thread, owner_id, [{"type": "text", "text": "问题"}], {}, assistant_id
    )
    assistant = AgentMessage(
        id=assistant_id, thread_id=thread.id, run_id=run.id, role="assistant",
        parts=[{"type": "text", "text": "回答"}], created_at=datetime.now(UTC),
    )
    assert repository.complete_run(run.id, assistant)
    return run.id


def _thread_events(database, thread_id: str) -> list[dict]:
    return list(
        database.agent_thread_events.find({"threadId": thread_id}, {"_id": 0})
        .sort("eventSeq", 1)
    )


def _assert_thread_event_order(database, thread_id: str, run_id: str) -> None:
    events = _thread_events(database, thread_id)
    assert [event["eventSeq"] for event in events] == [1, 2, 3, 4]
    assert [event["type"] for event in events] == EVENT_TYPES
    assert all(event["runId"] == run_id for event in events)


def test_two_threads_have_independent_monotonic_event_sequences() -> None:
    mongo, repository = _repository()
    case_id, owner_id = _scope()
    try:
        database = mongo.get_default_database()
        first = repository.default_thread(case_id, owner_id)
        second = repository.create_thread(case_id, owner_id, "第二对话")
        first_run = _run_turn(repository, first, owner_id)
        second_run = _run_turn(repository, second, owner_id)
        _assert_thread_event_order(database, first.id, first_run)
        _assert_thread_event_order(database, second.id, second_run)
    finally:
        mongo.close()


def test_failed_proposal_cannot_miss_a_concurrent_document_edit(monkeypatch) -> None:
    from app.modules.agent.artifacts import decide_artifact
    from app.modules.agent.models import AgentArtifact, ArtifactTarget
    from app.modules.cases.service import CaseError, create_case, update_case

    mongo, repository = _repository()
    database = mongo.get_default_database()
    _, owner_id = _scope()
    user = {"id": owner_id, "role": "teacher"}
    document = {"type": "doc", "content": [{"type": "paragraph"}, {"type": "paragraph"}]}
    case = create_case(database, {"title": "候选并发保存", "document": document}, user)
    thread = repository.default_thread(case["id"], owner_id)
    assistant_id = new_id("message")
    run = repository.start_run(thread, owner_id, [{"type": "text", "text": "补写首段"}], {}, assistant_id)
    artifact = AgentArtifact(
        id=new_id("artifact"), case_id=case["id"], thread_id=thread.id, run_id=run.id,
        base_revision=case["revision"], target=ArtifactTarget(from_pos=1, to_pos=1, quote=""),
        replacement="只能补在原来的首段", created_at=datetime.now(UTC),
    )
    assistant = AgentMessage(
        id=assistant_id, thread_id=thread.id, run_id=run.id, role="assistant",
        parts=[{"type": "text", "text": "已生成建议"}], created_at=datetime.now(UTC),
    )
    original = repository._persist_assistant
    changed = False

    def edit_after_snapshot(*args, **kwargs):
        nonlocal changed
        original(*args, **kwargs)
        if changed:
            return
        changed = True
        # 失败事务已经读取快照，另一个事务删除首段；第二个空段移到同一坐标。
        update_case(database, case["id"], {
            "revision": case["revision"],
            "document": {"type": "doc", "content": [{"type": "paragraph"}]},
            "steps": [{"stepType": "replace", "from": 0, "to": 2}],
        }, user)

    monkeypatch.setattr(repository, "_persist_assistant", edit_after_snapshot)
    try:
        assert repository.fail_run(run.id, assistant=assistant, artifacts=[artifact])
        with pytest.raises(CaseError):
            decide_artifact(database, case["id"], thread.id, artifact.id, user, "accepted")
        saved = database.agent_artifacts.find_one({"id": artifact.id})
        assert saved["status"] == "expired"
        assert database.cases.find_one({"id": case["id"]})["document"] == {
            "type": "doc", "content": [{"type": "paragraph"}],
        }
    finally:
        for collection in ("agent_messages", "agent_thread_events", "agent_runs", "agent_artifacts"):
            database[collection].delete_many({"threadId": thread.id})
        database.agent_threads.delete_one({"id": thread.id})
        database.cases.delete_one({"id": case["id"]})
        mongo.close()
