from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel


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


def _body(text: str = "你好", history: list[dict] | None = None) -> dict:
    return {
        "id": "browser-chat-id",
        "trigger": "submit-message",
        "messages": [*(history or []), _message(text)],
    }


def _post(client: TestClient, auth: dict, text: str = "你好", history=None):
    thread_id = client.get(THREAD_PATH).json()["id"]
    return client.post(
        f"{THREAD_PATH}/{thread_id}/stream",
        headers=_csrf(auth),
        json=_body(text, history),
    )


def _assert_completed(database, answer: str) -> None:
    messages = list(database.agent_messages.find({}, {"_id": 0}).sort("createdAt", 1))
    run = database.agent_runs.find_one({}, {"_id": 0})
    assert [row["role"] for row in messages] == ["user", "assistant"]
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


def test_agent_route_requires_login_and_csrf(client: TestClient) -> None:
    assert client.get(THREAD_PATH).status_code == 401
    auth = _login(client)
    thread_id = client.get(THREAD_PATH).json()["id"]

    response = client.post(f"{THREAD_PATH}/{thread_id}/stream", json=_body())

    assert response.status_code == 403
    assert auth["user"]["id"]


def test_legacy_generic_chat_route_is_preserved(client: TestClient) -> None:
    assert "/api/ai/chat" in client.app.openapi()["paths"]
