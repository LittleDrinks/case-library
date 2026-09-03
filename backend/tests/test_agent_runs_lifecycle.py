"""Run 生命周期：断开不取消、显式停止、停止竞态、重试、afterSeq 恢复与终态顺序。"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from pydantic_ai import CancellationToken
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.modules.agent import service
from app.modules.agent.repository import AgentRepository
from app.modules.agent.service import RunContext


THREAD_PATH = "/api/cases/c-draft-1/agent/thread"


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def _csrf(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def _thread_id(client: TestClient) -> str:
    return client.get(THREAD_PATH).json()["id"]


def _post_body(text: str, message_id: str = "lifecycle-message") -> dict:
    return {
        "id": "browser-chat-id",
        "trigger": "submit-message",
        "messages": [{"id": message_id, "role": "user", "parts": [
            {"type": "text", "text": text},
        ]}],
    }


def _post(client: TestClient, auth: dict, text: str, message_id: str = "lifecycle-message"):
    return client.post(
        f"{THREAD_PATH}/{_thread_id(client)}/stream",
        headers=_csrf(auth), json=_post_body(text, message_id),
    )


def _post_async(app, text: str, model, message_id: str = "lifecycle-message"):
    """在独立线程发起流式请求；model override 须在请求线程上下文内生效。"""
    client = TestClient(app)

    def send():
        auth = _login(client)
        with app.state.agent.override(model=model):
            return client.post(
                f"{THREAD_PATH}/{_thread_id(client)}/stream",
                headers=_csrf(auth), json=_post_body(text, message_id),
            )

    pool = ThreadPoolExecutor(max_workers=1)
    return pool.submit(send), client, pool


def _gated_model(release: Event, reached: Event | None = None, tail: Event | None = None):
    """确定性阻塞模型：两段文本，中间阻塞直到 release；tail 阻塞流结束。"""

    async def stream(_messages, _info):
        yield "前半"
        if reached:
            reached.set()
        await asyncio.to_thread(release.wait, 60)
        yield "后半"
        if tail:
            await asyncio.to_thread(tail.wait, 60)

    return FunctionModel(stream_function=stream)


def _failing_model():

    async def stream(_messages, _info):
        raise RuntimeError("provider unavailable")
        yield "unreachable"

    return FunctionModel(stream_function=stream)


def _await_run(database, thread_id: str, deadline: float = 10) -> dict | None:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": {"$ne": "active"}},
            {"_id": 0}, sort=[("startedAt", -1), ("id", -1)],
        )
        if run:
            return run
        Event().wait(0.02)
    return None


def _await_active(database, thread_id: str, deadline: float = 10) -> dict:
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        run = database.agent_runs.find_one(
            {"threadId": thread_id, "status": "active"}, {"_id": 0}
        )
        if run:
            return run
        Event().wait(0.02)
    raise AssertionError("run did not become active")


def _await_thread_with_active(client: TestClient) -> str:
    database = client.app.state.database
    end = time.monotonic() + 10
    while time.monotonic() < end:
        thread = database.agent_threads.find_one({"caseId": "c-draft-1"}, {"_id": 0})
        if thread and thread.get("activeRunId"):
            return thread["id"]
        Event().wait(0.02)
    raise AssertionError("no active thread appeared")


def _events(database, thread_id: str) -> list[dict]:
    return list(database.agent_thread_events.find(
        {"threadId": thread_id}, {"_id": 0}
    ).sort("eventSeq", 1))


def _asgi_scope(headers: dict, thread_id: str) -> dict:
    header_items = [
        (name.lower().encode(), value.encode()) for name, value in headers.items()
    ]
    return {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": "POST",
        "path": f"{THREAD_PATH}/{thread_id}/stream", "raw_path": b"",
        "query_string": b"", "root_path": "", "headers": header_items,
        "client": ("testclient", 1), "server": ("testserver", 80),
    }


def _asgi_receive(body: bytes, disconnect: Event):
    calls = {"count": 0}

    async def receive():
        if calls["count"] == 0:
            calls["count"] = 1
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.to_thread(disconnect.wait)
        return {"type": "http.disconnect"}

    return receive


def _drive_disconnect(app, thread_id: str, auth: dict, body: bytes, model, disconnect: Event):
    """原生 ASGI 驱动：首块响应后发送 http.disconnect，loop 存活到 stop()。"""
    scope = _asgi_scope(
        {"X-CSRF-Token": auth["csrfToken"], "Cookie": auth["cookie"]}, thread_id
    )
    state = {"first": Event(), "chunks": 0}

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            state["chunks"] += 1
            if state["chunks"] == 1:
                state["first"].set()

    return _spawn_disconnected_app(app, scope, body, model, disconnect, send, state)


def _spawn_disconnected_app(app, scope, body, model, disconnect, send, state):
    async def run_app():
        with app.state.agent.override(model=model):
            await app(scope, _asgi_receive(body, disconnect), send)

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    future = asyncio.run_coroutine_threadsafe(run_app(), loop)
    return state, future, loop


def _stop_loop(loop: asyncio.AbstractEventLoop, future) -> None:
    future.result(timeout=15)
    loop.call_soon_threadsafe(loop.stop)


def _login_cookie(client: TestClient) -> dict:
    auth = _login(client)
    cookie = client.cookies.get("case_library_session")
    return {**auth, "cookie": f"case_library_session={cookie}"}


def _assert_terminal_completed(database, thread_id: str, run: dict) -> None:
    finished = _await_run(database, thread_id)
    assert finished["status"] == "completed", finished
    assert finished["id"] == run["id"]
    messages = list(database.agent_messages.find(
        {"threadId": thread_id}, {"_id": 0}
    ))
    assert [row["role"] for row in messages] == ["user", "assistant"]
    assert messages[-1]["parts"][-1]["text"] == "前半后半"
    assert [event["type"] for event in _events(database, thread_id)] == [
        "message.created", "run.started", "message.created", "run.completed",
    ]


def test_client_disconnect_keeps_run_running_to_terminal(client: TestClient) -> None:
    auth = _login_cookie(client)
    release, reached, disconnect = Event(), Event(), Event()
    model = _gated_model(release, reached)
    thread_id = _thread_id(client)
    state, future, loop = _drive_disconnect(
        client.app, thread_id, auth,
        json.dumps(_post_body("断开测试")).encode(), model, disconnect,
    )
    try:
        _assert_disconnect_survives(client, thread_id, state, reached, disconnect, release)
        database = client.app.state.database
        run = _await_active(database, thread_id)
        release.set()
        _assert_terminal_completed(database, thread_id, run)
    finally:
        release.set()
        disconnect.set()
        _stop_loop(loop, future)


def _assert_disconnect_survives(client, thread_id, state, reached, disconnect, release) -> None:
    assert state["first"].wait(10), "no response chunk arrived"
    assert reached.wait(10), "model never reached the gate"
    disconnect.set()
    database = client.app.state.database
    _await_active(database, thread_id)
    assert [event["type"] for event in _events(database, thread_id)][-1] == "run.started"


def _stop_active_run(client: TestClient, auth: dict) -> str:
    thread_id = _await_thread_with_active(client)
    cancelled = client.post(
        f"{THREAD_PATH}/{thread_id}/cancel", headers=_csrf(auth)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelling"
    return thread_id


def test_explicit_stop_cancels_run_and_cancel_is_idempotent(client: TestClient) -> None:
    auth = _login(client)
    release = Event()
    model = _gated_model(release)
    with client.app.state.agent.override(model=model):
        future, _client, pool = _post_async(client.app, "停止测试", model)
        try:
            thread_id = _stop_active_run(client, auth)
            database = client.app.state.database
            run = _await_run(database, thread_id)
            assert run["status"] == "cancelled", run
            assert run["error"] == "运行已取消"
            assert _events(database, thread_id)[-1]["type"] == "run.cancelled"
            again = client.post(f"{THREAD_PATH}/{thread_id}/cancel", headers=_csrf(auth))
            assert again.json() == {"runId": None, "status": "idle"}
        finally:
            release.set()
            future.result(timeout=15)
            pool.shutdown()


def test_stop_race_completion_wins_when_stream_finishes_first(client: TestClient) -> None:
    auth = _login(client)
    with client.app.state.agent.override(model=TestModel(custom_output_text="竞态回答")):
        thread_id = _thread_id(client)
        assert _post(client, auth, "竞态测试").status_code == 200
    database = client.app.state.database
    run = _await_run(database, thread_id)
    assert run["status"] == "completed"

    cancelled = client.post(f"{THREAD_PATH}/{thread_id}/cancel", headers=_csrf(auth))
    assert cancelled.json() == {"runId": None, "status": "idle"}
    assert database.agent_runs.find_one({"id": run["id"]}, {"_id": 0})["status"] == "completed"
    assert not [event for event in _events(database, thread_id)
                if event["type"] == "run.cancelled"]


def test_stop_race_cancellation_wins_when_token_fires_before_stream_end(client: TestClient) -> None:
    auth = _login(client)
    release, tail = Event(), Event()
    model = _gated_model(release, tail=tail)
    with client.app.state.agent.override(model=model):
        future, _client, pool = _post_async(client.app, "停止竞态", model)
        try:
            thread_id = _stop_active_run(client, auth)
            run = _await_run(client.app.state.database, thread_id)
            assert run["status"] == "cancelled"
            tail.set()
        finally:
            release.set()
            future.result(timeout=15)
            pool.shutdown()
    assert not client.app.state.database.agent_messages.find_one({
        "threadId": thread_id, "role": "assistant",
    })


def _retry_request(client: TestClient, auth: dict, message_id: str):
    return client.post(
        f"{THREAD_PATH}/{_thread_id(client)}/stream",
        headers=_csrf(auth),
        json={
            "id": "browser-chat-id",
            "trigger": "regenerate-message",
            "messageId": message_id,
            "messages": [],
        },
    )


def _failed_first_run(client: TestClient, auth: dict, database) -> tuple[str, dict, dict]:
    with client.app.state.agent.override(model=_failing_model()):
        assert _post(client, auth, "重试测试", message_id="retry-original").status_code == 200
    thread_id = _thread_id(client)
    failed = _await_run(database, thread_id)
    assert failed["status"] == "failed"
    user_message = database.agent_messages.find_one(
        {"threadId": thread_id, "role": "user"}, {"_id": 0}
    )
    return thread_id, failed, user_message


def _assert_retry_records(database, thread_id, failed, retried, user_message) -> None:
    messages = list(database.agent_messages.find(
        {"threadId": thread_id}, {"_id": 0}
    ).sort("messageSeq", 1))
    assert [row["role"] for row in messages] == ["user", "assistant"]
    assert messages[0]["id"] == user_message["id"]
    assert messages[0]["runId"] == failed["id"]
    assert messages[1]["runId"] == retried["id"]
    assert retried["userMessageId"] == user_message["id"]
    assert retried["id"] != failed["id"]


def _assert_retry_events(database, thread_id, failed, retried) -> None:
    assert [event["type"] for event in _events(database, thread_id)] == [
        "message.created", "run.started", "run.failed",
        "run.started", "message.created", "run.completed",
    ]
    assert [event["runId"] for event in _events(database, thread_id)] == [
        failed["id"], failed["id"], failed["id"],
        retried["id"], retried["id"], retried["id"],
    ]


def test_retry_failed_message_creates_new_run_referencing_original(client: TestClient) -> None:
    auth = _login(client)
    database = client.app.state.database
    thread_id, failed, user_message = _failed_first_run(client, auth, database)

    with client.app.state.agent.override(model=TestModel(custom_output_text="重试成功")):
        assert _retry_request(client, auth, user_message["id"]).status_code == 200
    retried = _await_run(database, thread_id)
    assert retried["status"] == "completed"

    _assert_retry_records(database, thread_id, failed, retried, user_message)
    snapshot = client.get(THREAD_PATH).json()
    assert [row["id"] for row in snapshot["runs"]] == [failed["id"], retried["id"]]
    assert snapshot["latestRun"]["status"] == "completed"
    _assert_retry_events(database, thread_id, failed, retried)


def test_retry_rejects_unknown_or_non_user_message(client: TestClient) -> None:
    auth = _login(client)
    assert _retry_request(client, auth, "missing-message").status_code == 422
    assert _retry_request(client, auth, "").status_code == 422


def _sse_chunks(response) -> list:
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"]


def _assert_replayed_assistant(chunks: list, snapshot: dict) -> None:
    assistant_id = snapshot["latestRun"]["assistantMessageId"]
    assert chunks[0] == {"type": "start", "messageId": assistant_id}
    assert {"type": "text-delta", "id": chunks[1]["id"], "delta": "恢复回答"} in chunks
    assert chunks[-1] == {"type": "finish", "finishReason": "stop"}


def test_events_endpoint_replays_from_after_seq(client: TestClient) -> None:
    auth = _login(client)
    with client.app.state.agent.override(model=TestModel(custom_output_text="恢复回答")):
        assert _post(client, auth, "恢复测试").status_code == 200
    thread_id = _thread_id(client)
    snapshot = client.get(THREAD_PATH).json()
    path = f"{THREAD_PATH}/{thread_id}/events"
    replay = client.get(path, params={"afterSeq": 0})
    assert replay.status_code == 200
    assert replay.headers["x-vercel-ai-ui-message-stream"] == "v1"
    _assert_replayed_assistant(_sse_chunks(replay), snapshot)
    assert replay.text.endswith("data: [DONE]\n\n")
    _assert_exhausted(client, path, snapshot["eventSeq"])


def _assert_exhausted(client: TestClient, path: str, event_seq: int) -> None:
    current = client.get(path, params={"afterSeq": event_seq})
    assert current.status_code == 204
    header_cursor = client.get(path, headers={"Last-Event-ID": str(event_seq)})
    assert header_cursor.status_code == 204


def test_events_endpoint_tails_active_run_and_stops_at_done(client: TestClient) -> None:
    _login(client)
    release = Event()
    model = _gated_model(release)
    with client.app.state.agent.override(model=model):
        future, _client, pool = _post_async(client.app, "事件尾测试", model)
        try:
            thread_id = _await_thread_with_active(client)
            _assert_events_tail(client, thread_id, release)
        finally:
            release.set()
            future.result(timeout=30)
            pool.shutdown()


def _assert_events_tail(client: TestClient, thread_id: str, release: Event) -> None:
    database = client.app.state.database
    before = database.agent_threads.find_one({"id": thread_id}, {"_id": 0})
    with client.stream(
        "GET", f"{THREAD_PATH}/{thread_id}/events",
        params={"afterSeq": before["eventSeq"]}, timeout=30,
    ) as response:
        assert response.status_code == 200
        release.set()
        lines = [line for line in response.iter_lines() if line]
    chunks = [json.loads(line[6:]) for line in lines if line != "data: [DONE]"]
    assert lines[-1] == "data: [DONE]"
    assert chunks[0]["type"] == "start"
    assert [chunk["type"] for chunk in chunks].count("text-delta") == 1
    assert chunks[-1] == {"type": "finish", "finishReason": "stop"}
    run = database.agent_runs.find_one({"threadId": thread_id}, {"_id": 0})
    assert run["status"] == "completed"


def test_terminal_event_seals_the_thread_event_tail(client: TestClient) -> None:
    auth = _login(client)
    with client.app.state.agent.override(model=TestModel(custom_output_text="终态回答")):
        assert _post(client, auth, "终态顺序").status_code == 200
    database = client.app.state.database
    thread_id = _thread_id(client)
    events = _events(database, thread_id)
    assert [event["type"] for event in events][-2:] == [
        "message.created", "run.completed",
    ]
    terminal_seq = events[-1]["eventSeq"]
    assert not AgentRepository(database).append_event(
        thread_id, "message.created", events[-1]["runId"], {"messageId": "late"}
    )
    assert database.agent_threads.find_one({"id": thread_id})["eventSeq"] == terminal_seq


def _renew_context(repository, run, token: CancellationToken, worker_id: str) -> RunContext:
    return RunContext(
        repository=repository, run=run, adapter=None, history=[], prompt="",
        case={}, agent=None, token=token, worker_id=worker_id,
    )


def _active_run_for(repository, auth: dict):
    thread = repository.default_thread("c-draft-1", auth["user"]["id"])
    return repository.start_run(
        thread, auth["user"]["id"], [{"type": "text", "text": "跨worker"}], {},
        "assistant-message", owner_id="worker-a",
    )


def test_monitor_observes_cross_worker_cancel_request(client: TestClient) -> None:
    auth = _login(client)
    repository = AgentRepository(client.app.state.database)
    run = _active_run_for(repository, auth)
    token = CancellationToken()
    context = _renew_context(repository, run, token, "worker-a")
    assert service._renew(context) is True
    assert not token.cancelled

    assert repository.request_cancel(run.id) is not None
    assert service._renew(context) is True
    assert token.cancelled


def test_monitor_loses_run_after_owner_expiry(client: TestClient) -> None:
    auth = _login(client)
    repository = AgentRepository(client.app.state.database)
    run = _active_run_for(repository, auth)
    expired = service._renew(_renew_context(repository, run, CancellationToken(), "worker-b"))
    assert expired is False


def test_cancel_endpoint_is_forbidden_for_non_author(client: TestClient) -> None:
    _login(client)
    thread_id = _thread_id(client)
    admin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()
    response = client.post(f"{THREAD_PATH}/{thread_id}/cancel", headers=_csrf(admin))
    assert response.status_code == 403
    events = client.get(f"{THREAD_PATH}/{thread_id}/events", params={"afterSeq": 0})
    assert events.status_code == 403
