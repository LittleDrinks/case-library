from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import patch

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


def test_legacy_generic_chat_route_is_preserved(client: TestClient) -> None:
    assert "/api/ai/chat" in client.app.openapi()["paths"]


def test_active_run_uniqueness_is_database_enforced(client: TestClient) -> None:
    database = client.app.state.database
    database.agent_runs.insert_one({"id": "run-a", "threadId": "thread-a", "status": "active"})

    try:
        database.agent_runs.insert_one({"id": "run-b", "threadId": "thread-a", "status": "active"})
    except DuplicateKeyError:
        return
    raise AssertionError("active Run index did not reject a second run")
