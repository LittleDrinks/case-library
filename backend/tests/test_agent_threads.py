from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from app.modules.agent.repository import AgentRepository


THREADS_PATH = "/api/cases/c-draft-1/agent/threads"
DEFAULT_PATH = "/api/cases/c-draft-1/agent/thread"


def _agent():
    from app.modules.agent.runtime import agent

    return agent


def _login(client: TestClient, username: str = "user", password: str = "user123") -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _create_thread(client: TestClient, auth: dict, title: str | None = None) -> dict:
    body = {} if title is None else {"title": title}
    response = client.post(THREADS_PATH, headers=_csrf(auth), json=body)
    assert response.status_code == 201
    return response.json()


def _send(client: TestClient, auth: dict, thread_id: str, text: str, message_id: str):
    return client.post(
        f"{DEFAULT_PATH}/{thread_id}/stream",
        headers=_csrf(auth),
        json={
            "id": "browser-chat-id",
            "trigger": "submit-message",
            "messages": [
                {"id": message_id, "role": "user", "parts": [{"type": "text", "text": text}]}
            ],
        },
    )


def _snapshot(client: TestClient, thread_id: str) -> dict:
    response = client.get(f"{THREADS_PATH}/{thread_id}")
    assert response.status_code == 200
    return response.json()


def test_thread_list_and_create_roundtrip(client: TestClient) -> None:
    auth = _login(client)
    default_id = client.get(DEFAULT_PATH).json()["id"]
    created = _create_thread(client, auth, "资料梳理")

    threads = client.get(THREADS_PATH).json()

    assert len(threads) == 2
    summary = next(item for item in threads if item["id"] == created["id"])
    assert summary["title"] == "资料梳理"
    assert summary["isDefault"] is False
    assert summary["running"] is False
    snapshot = _snapshot(client, created["id"])
    assert snapshot["title"] == "资料梳理"
    assert snapshot["messages"] == [] and snapshot["artifacts"] == []
    default = next(item for item in threads if item["isDefault"])
    assert default["id"] == default_id


def test_first_message_titles_untitled_thread(client: TestClient) -> None:
    auth = _login(client)
    default_id = client.get(DEFAULT_PATH).json()["id"]
    created = _create_thread(client, auth)
    with _agent().override(model=TestModel(custom_output_text="回答")):
        assert _send(client, auth, created["id"], "首条消息成为标题", "m-1").status_code == 200

    titled = {item["id"]: item["title"] for item in client.get(THREADS_PATH).json()}

    assert titled[created["id"]] == "首条消息成为标题"
    assert titled[default_id] is None


def test_first_message_titles_default_thread(client: TestClient) -> None:
    auth = _login(client)
    default_id = client.get(DEFAULT_PATH).json()["id"]
    with _agent().override(model=TestModel(custom_output_text="回答")):
        assert _send(client, auth, default_id, "默认对话首条消息", "m-1").status_code == 200

    snapshot = _snapshot(client, default_id)

    assert snapshot["title"] == "默认对话首条消息"


def test_rename_thread_validation_and_not_found(client: TestClient) -> None:
    auth = _login(client)
    created = _create_thread(client, auth, "旧标题")

    renamed = client.patch(
        f"{THREADS_PATH}/{created['id']}", headers=_csrf(auth), json={"title": " 新标题 "}
    )

    assert renamed.status_code == 200 and renamed.json()["title"] == "新标题"
    assert _snapshot(client, created["id"])["title"] == "新标题"
    path = f"{THREADS_PATH}/{created['id']}"
    assert client.patch(path, headers=_csrf(auth), json={"title": "  "}).status_code == 422
    assert client.patch(path, headers=_csrf(auth), json={"title": "长" * 61}).status_code == 422
    missing = client.patch(
        f"{THREADS_PATH}/thread-missing", headers=_csrf(auth), json={"title": "x"}
    )
    assert missing.status_code == 404


def test_cross_case_and_cross_user_threads_are_not_enumerable(client: TestClient) -> None:
    auth = _login(client)
    created = _create_thread(client, auth, "案例一的对话")
    document = {"type": "doc", "content": [{"type": "paragraph"}]}
    second = client.post(
        "/api/cases", headers=_csrf(auth), json={"title": "第二个案例", "document": document}
    )
    assert second.status_code == 200
    other = f"/api/cases/{second.json()['id']}/agent/threads/{created['id']}"

    assert client.get(other).status_code == 404
    assert client.patch(other, headers=_csrf(auth), json={"title": "x"}).status_code == 404
    _login(client, "admin", "admin123")
    assert client.get(THREADS_PATH).status_code == 403
    assert client.get(f"{THREADS_PATH}/{created['id']}").status_code == 403


def test_thread_mutations_require_login_and_csrf(client: TestClient) -> None:
    assert client.get(THREADS_PATH).status_code == 401
    auth = _login(client)
    assert client.post(THREADS_PATH, json={}).status_code == 403

    created = _create_thread(client, auth, "x")

    assert client.patch(
        f"{THREADS_PATH}/{created['id']}", json={"title": "y"}
    ).status_code == 403


def _user_texts(snapshot: dict) -> list[str]:
    return [m["parts"][0]["text"] for m in snapshot["messages"] if m["role"] == "user"]


def test_two_threads_keep_isolated_messages_runs_and_events(client: TestClient) -> None:
    auth = _login(client)
    created = _create_thread(client, auth, "第二个对话")
    default_id = client.get(DEFAULT_PATH).json()["id"]
    with _agent().override(model=TestModel(custom_output_text="回答")):
        assert _send(client, auth, default_id, "默认对话问题", "m-default").status_code == 200
        assert _send(client, auth, created["id"], "第二对话问题", "m-second").status_code == 200

    default_snapshot = _snapshot(client, default_id)
    second_snapshot = _snapshot(client, created["id"])

    assert _user_texts(default_snapshot) == ["默认对话问题"]
    assert _user_texts(second_snapshot) == ["第二对话问题"]
    assert default_snapshot["latestRun"]["id"] != second_snapshot["latestRun"]["id"]
    summaries = {t["id"]: t for t in client.get(THREADS_PATH).json()}
    assert summaries[created["id"]]["title"] == "第二个对话"
    assert all(not t["running"] for t in summaries.values())


def test_list_marks_thread_with_active_run_as_running(client: TestClient) -> None:
    auth = _login(client)
    repository = AgentRepository(client.app.state.database)
    thread = repository.default_thread("c-draft-1", auth["user"]["id"])
    repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "x"}], {}, "assistant-1"
    )

    summaries = {t["id"]: t for t in client.get(THREADS_PATH).json()}

    assert summaries[thread.id]["running"] is True


def _insert_artifact(database, thread_id: str, artifact_id: str) -> None:
    database.agent_artifacts.insert_one({
        "id": artifact_id, "caseId": "c-draft-1", "threadId": thread_id, "runId": "run-x",
        "status": "pending", "baseRevision": 1,
        "target": {"paragraphIndex": 0, "quote": "原文"},
        "replacement": "替换", "reason": "", "sources": [],
        "createdAt": datetime.now(UTC),
    })


def test_thread_snapshots_scope_artifacts_to_their_thread(client: TestClient) -> None:
    auth = _login(client)
    repository = AgentRepository(client.app.state.database)
    first = repository.default_thread("c-draft-1", auth["user"]["id"])
    second = repository.create_thread("c-draft-1", auth["user"]["id"], "第二对话")
    _insert_artifact(client.app.state.database, first.id, "artifact-a")
    _insert_artifact(client.app.state.database, second.id, "artifact-b")

    first_snapshot = _snapshot(client, first.id)
    second_snapshot = _snapshot(client, second.id)

    assert [a["id"] for a in first_snapshot["artifacts"]] == ["artifact-a"]
    assert [a["id"] for a in second_snapshot["artifacts"]] == ["artifact-b"]


def test_default_thread_upsert_returns_same_thread(client: TestClient) -> None:
    auth = _login(client)
    repository = AgentRepository(client.app.state.database)
    first = repository.default_thread("c-draft-1", auth["user"]["id"])

    again = repository.default_thread("c-draft-1", auth["user"]["id"])

    assert again.id == first.id
