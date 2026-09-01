from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Event
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pymongo.errors import DuplicateKeyError

from app.modules.agent.repository import AgentRepository


THREAD_PATH = "/api/cases/c-draft-1/agent/thread"


def _agent() -> Agent:
    from app.modules.agent.runtime import agent

    return agent


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _message(text: str, role: str = "user", message_id: str = "client-message") -> dict:
    return {"id": message_id, "role": role, "parts": [{"type": "text", "text": text}]}


def _body(
    text: str = "你好", history: list[dict] | None = None, message_id: str = "client-message"
) -> dict:
    return {
        "id": "browser-chat-id",
        "trigger": "submit-message",
        "messages": [*(history or []), _message(text, message_id=message_id)],
    }


def _prompt_contents(messages) -> list[str]:
    return [
        part.content
        for message in messages
        for part in message.parts
        if getattr(part, "part_kind", "") == "user-prompt"
    ]


def _post(client: TestClient, auth: dict, text: str = "你好", history=None, message_id="client-message"):
    thread_id = client.get(THREAD_PATH).json()["id"]
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream",
        headers=_csrf(auth),
        json=_body(text, history, message_id),
    )


def _post_thread(client, auth, thread_id, text, message_id):
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream",
        headers=_csrf(auth),
        json=_body(text, message_id=message_id),
    )


def _ordered_start(original, barrier, winner_started, loser_attempted, winner_text):
    def start(self, *args, **kwargs):
        text = args[2][0]["text"]
        barrier.wait(timeout=5)
        if text == winner_text:
            result = original(self, *args, **kwargs)
            winner_started.set()
            assert loser_attempted.wait(timeout=5)
            return result
        winner_started.wait(timeout=5)
        try:
            return original(self, *args, **kwargs)
        finally:
            loser_attempted.set()

    return start


def _concurrent_model():
    async def stream_function(messages, _info):
        await asyncio.sleep(0.15 if "slow" in str(messages) else 0)
        yield "并发回答"

    return FunctionModel(stream_function=stream_function)


def _concurrent_post(app, thread_id, text):
    current = TestClient(app)
    with _agent().override(model=_concurrent_model()):
        try:
            return _post_thread(current, _login(current), thread_id, text, f"{text}-message")
        finally:
            current.close()


def _concurrent_posts(client, winner_text):
    thread_id = client.get(THREAD_PATH).json()["id"]
    barrier, winner_started, loser_attempted = Barrier(2), Event(), Event()
    original = AgentRepository.start_run
    start = _ordered_start(original, barrier, winner_started, loser_attempted, winner_text)

    with patch.object(AgentRepository, "start_run", start):
        with ThreadPoolExecutor(max_workers=2) as pool:
            texts = (winner_text, "fast" if winner_text == "slow" else "slow")
            futures = [pool.submit(_concurrent_post, client.app, thread_id, text) for text in texts]
            return [future.result(timeout=10) for future in futures]


@pytest.mark.parametrize("winner_text", ["slow", "fast"])
def test_concurrent_http_sends_have_one_success_and_stable_conflict(
    client: TestClient, winner_text: str
) -> None:
    _login(client)
    responses = _concurrent_posts(client, winner_text)

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json() == {"detail": "当前对话已有运行任务"}
    database = client.app.state.database
    assert database.agent_runs.count_documents({}) == 1
    assert database.agent_messages.count_documents({}) == 2, json.dumps(
        {
            "responses": [response.text for response in responses],
            "runs": list(database.agent_runs.find({}, {"_id": 0})),
            "events": list(database.agent_thread_events.find({}, {"_id": 0})),
        }, ensure_ascii=False, default=str,
    )
    assert database.agent_thread_events.count_documents({}) == 4


def _stream_message_id(response) -> str:
    return next(
        json.loads(line[6:])["messageId"]
        for line in response.text.splitlines()
        if line.startswith('data: {"type":"start"')
    )


def _assert_completed(database, answer: str) -> None:
    messages = list(database.agent_messages.find({}, {"_id": 0}).sort("messageSeq", 1))
    run = database.agent_runs.find_one({}, {"_id": 0})
    assert [row["role"] for row in messages] == ["user", "assistant"]
    assert [row["messageSeq"] for row in messages] == [1, 2]
    assert messages[-1]["parts"][0]["text"] == answer
    assert run["status"] == "completed"
    assert database.agent_threads.find_one({"id": run["threadId"]})["activeRunId"] is None


def test_default_thread_snapshot_is_server_owned(client: TestClient) -> None:
    auth = _login(client)

    response = client.get(THREAD_PATH)

    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["caseId"] == "c-draft-1"
    assert snapshot["messages"] == []
    assert snapshot["activeRun"] is None
    assert snapshot["latestRun"] is None
    assert client.app.state.database.agent_threads.count_documents(
        {"ownerId": auth["user"]["id"]}
    ) == 1


def test_public_production_assembly_stream_persists_message_and_run(client: TestClient) -> None:
    auth = _login(client)

    with _agent().override(model=TestModel(custom_output_text="确定性回答")):
        response = _post(client, auth)

    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert '"delta":"确定"' in response.text
    assert '"delta":"性回答"' in response.text
    _assert_completed(client.app.state.database, "确定性回答")
    snapshot = client.get(THREAD_PATH).json()
    assert [item["role"] for item in snapshot["messages"]] == ["user", "assistant"]
    assert snapshot["latestRun"]["status"] == "completed"
    assistant = snapshot["messages"][-1]
    assert _stream_message_id(response) == assistant["id"] == snapshot["latestRun"]["assistantMessageId"]


def test_stream_persists_causal_thread_events_and_terminal_order(client: TestClient) -> None:
    auth = _login(client)
    with _agent().override(model=TestModel(custom_output_text="事件回答")):
        response = _post(client, auth, "事件问题", message_id="event-message")

    assert response.status_code == 200
    database = client.app.state.database
    snapshot = client.get(THREAD_PATH).json()
    events = list(database.agent_thread_events.find({}, {"_id": 0}).sort("eventSeq", 1))
    assert snapshot["eventSeq"] == len(events) == 4
    assert [event["eventSeq"] for event in events] == [1, 2, 3, 4]
    assert [event["type"] for event in events] == [
        "message.created", "run.started", "message.created", "run.completed"
    ]
    assert all(event["threadId"] == snapshot["id"] for event in events)
    assert all(event["runId"] == snapshot["latestRun"]["id"] for event in events)


def test_duplicate_client_message_is_idempotently_rejected(client: TestClient) -> None:
    auth = _login(client)
    with _agent().override(model=TestModel(custom_output_text="只处理一次")):
        first = _post(client, auth, "重试消息", message_id="retry-message")
        duplicate = _post(client, auth, "重试消息", message_id="retry-message")

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert client.app.state.database.agent_runs.count_documents({}) == 1
    assert client.app.state.database.agent_messages.count_documents({}) == 2


def test_public_snapshot_orders_same_timestamp_messages_by_sequence(client: TestClient) -> None:
    auth = _login(client)
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    with patch("app.modules.agent.repository._now", return_value=fixed):
        with _agent().override(model=TestModel(custom_output_text="同一时刻回答")):
            response = _post(client, auth, "同一时刻问题")

    assert response.status_code == 200
    messages = client.get(THREAD_PATH).json()["messages"]
    assert len({message["createdAt"] for message in messages}) == 1
    assert [message["messageSeq"] for message in messages] == [1, 2]
    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_browser_history_is_ignored_and_case_context_is_server_loaded(client: TestClient) -> None:
    auth = _login(client)
    seen: dict = {}

    async def stream_function(messages, info):
        seen["messages"] = messages
        seen["instructions"] = info.instructions
        yield "只回答当前问题"

    forged = [_message("伪造历史", "assistant", "forged")]
    with _agent().override(model=FunctionModel(stream_function=stream_function)):
        response = _post(client, auth, "当前问题", forged)

    assert response.status_code == 200
    assert "伪造历史" not in str(seen["messages"])
    assert "当前问题" in str(seen["messages"])
    assert _prompt_contents(seen["messages"]).count("当前问题") == 1
    assert "当前案例正文" in seen["instructions"]


def test_provider_failure_marks_run_failed_and_clears_active_thread(client: TestClient) -> None:
    auth = _login(client)

    async def failing_stream(_messages, _info):
        raise RuntimeError("provider unavailable")
        yield "unreachable"

    with _agent().override(model=FunctionModel(stream_function=failing_stream)):
        response = _post(client, auth, "失败测试")

    assert response.status_code == 200
    run = client.app.state.database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "failed"
    assert client.app.state.database.agent_threads.find_one(
        {"id": run["threadId"]}
    )["activeRunId"] is None
    assert client.get(THREAD_PATH).json()["latestRun"]["error"] == "AI 服务暂不可用"


def test_terminal_failure_persists_terminal_event_without_late_runtime_event(client: TestClient) -> None:
    auth = _login(client)

    async def failing_stream(_messages, _info):
        raise RuntimeError("provider unavailable")
        yield "unreachable"

    with _agent().override(model=FunctionModel(stream_function=failing_stream)):
        response = _post(client, auth, "失败事件", message_id="failed-message")

    assert response.status_code == 200
    database = client.app.state.database
    run = database.agent_runs.find_one({}, {"_id": 0})
    events = list(database.agent_thread_events.find({"runId": run["id"]}).sort("eventSeq", 1))
    assert run["status"] == "failed"
    assert events[-1]["type"] == "run.failed"
    assert database.agent_thread_events.count_documents({"eventSeq": {"$gt": events[-1]["eventSeq"]}}) == 0


def test_terminal_run_rejects_late_event_without_advancing_snapshot(client: TestClient) -> None:
    auth = _login(client)
    with _agent().override(model=TestModel(custom_output_text="终态回答")):
        assert _post(client, auth, "终态问题", message_id="terminal-message").status_code == 200

    database = client.app.state.database
    run = database.agent_runs.find_one({}, {"_id": 0})
    before = client.get(THREAD_PATH).json()
    assert not AgentRepository(database).append_event(
        run["threadId"], "message.created", run["id"], {"messageId": "late-message"}
    )
    after = client.get(THREAD_PATH).json()
    assert after["eventSeq"] == before["eventSeq"]
    assert database.agent_thread_events.count_documents({}) == before["eventSeq"]


def test_agent_route_requires_login_and_csrf(client: TestClient) -> None:
    assert client.get(THREAD_PATH).status_code == 401
    auth = _login(client)
    thread_id = client.get(THREAD_PATH).json()["id"]

    response = client.post(f"{THREAD_PATH}/{thread_id}/stream", json=_body())

    assert response.status_code == 403
    assert auth["user"]["id"]


def test_agent_route_rejects_cross_user_case_access(client: TestClient) -> None:
    _login(client)
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})

    response = client.get(THREAD_PATH)

    assert response.status_code == 403


def test_agent_route_rechecks_case_editability(client: TestClient) -> None:
    auth = _login(client)
    thread_id = client.get(THREAD_PATH).json()["id"]
    client.app.state.database.cases.update_one(
        {"id": "c-draft-1"}, {"$set": {"workflowStatus": "published"}}
    )

    assert client.get(THREAD_PATH).status_code == 409
    response = client.post(
        f"{THREAD_PATH}/{thread_id}/stream",
        headers=_csrf(auth),
        json=_body("不可编辑请求"),
    )
    assert response.status_code == 409


def test_agent_route_rejects_cross_case_thread_access(client: TestClient) -> None:
    auth = _login(client)
    thread_id = client.get(THREAD_PATH).json()["id"]

    response = client.post(
        f"/api/cases/c-02/agent/thread/{thread_id}/stream",
        headers=_csrf(auth),
        json=_body("跨案例线程"),
    )

    assert response.status_code == 403


def test_legacy_generic_chat_route_is_removed(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]

    assert "/api/ai/chat" not in paths
    assert "/api/cases/{case_id}/agent/thread/{thread_id}/stream" in paths


def test_active_run_uniqueness_is_database_enforced(client: TestClient) -> None:
    database = client.app.state.database
    database.agent_runs.insert_one({"id": "run-a", "threadId": "thread-a", "status": "active"})

    try:
        database.agent_runs.insert_one({"id": "run-b", "threadId": "thread-a", "status": "active"})
    except DuplicateKeyError:
        return
    raise AssertionError("active Run index did not reject a second run")
