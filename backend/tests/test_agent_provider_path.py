from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi.testclient import TestClient
from pydantic_ai.models import override_allow_model_requests


class _ProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        self.server.seen.append(payload)
        if self.server.mode == "failure":
            self._failure()
            return
        self._success()

    def _failure(self) -> None:
        body = b'{"error":{"message":"upstream failed"}}'
        self.send_response(502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _success(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.server.seen[-1].get("enable_thinking"):
            for text in ("先核对", "资料区与选区"):
                self.wfile.write(_reasoning_chunk(text))
                self.wfile.flush()
        for text in ("生产", "模型回答"):
            chunk = _chunk(text)
            self.wfile.write(chunk)
            self.wfile.flush()


def _chunk(text: str) -> bytes:
    payload = {"choices": [{"index": 0, "delta": {"content": text}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _reasoning_chunk(text: str) -> bytes:
    payload = {"choices": [{"index": 0, "delta": {"reasoning_content": text}}]}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


class _ProviderServer:
    def __init__(self, mode="success") -> None:
        self.mode = mode
        self.server = None
        self.thread = None

    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
        self.server.mode = self.mode
        self.server.seen = []
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"


def _login(client: TestClient) -> dict:
    return client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    ).json()


def _configure(client: TestClient, auth: dict, base_url: str) -> None:
    _configure_model(client, auth, base_url, "model-a")


def _configure_model(client: TestClient, auth: dict, base_url: str, model: str) -> None:
    response = client.put(
        "/api/ai/settings",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"mode": "custom", "baseUrl": base_url, "apiKey": "provider-key", "model": model},
    )
    assert response.status_code == 200


def _body(text: str, message_id: str = "client-message") -> dict:
    return {
        "id": "browser-chat",
        "trigger": "submit-message",
        "messages": [{
            "id": message_id, "role": "user",
            "parts": [{"type": "text", "text": text}],
        }],
    }


def _send(client: TestClient, auth: dict) -> object:
    thread = client.get("/api/cases/c-draft-1/agent/thread").json()
    return client.post(
        f"/api/cases/c-draft-1/agent/thread/{thread['id']}/stream",
        headers={"X-CSRF-Token": auth["csrfToken"]}, json=_body("生产路径"),
    )


def test_custom_provider_uses_production_agent_route_and_releases_lease(
    client: TestClient,
) -> None:
    with _ProviderServer() as provider, override_allow_model_requests(True):
        auth = _login(client)
        _configure(client, auth, provider.base_url)
        response = _send(client, auth)
        assert response.status_code == 200
        assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
        assert '"delta":"生产"' in response.text
        assert '"delta":"模型回答"' in response.text
        assert provider.server.seen[0]["stream"] is True
        assert provider.server.seen[0]["model"] == "model-a"
    database = client.app.state.database
    run = database.agent_runs.find_one({}, {"_id": 0})
    assert run["status"] == "completed"
    assert database.ai_usage.count_documents({"token": {"$exists": True}}) == 0
    assert "ownerId" not in client.get("/api/cases/c-draft-1/agent/thread").text


def test_upstream_failure_is_a_stable_terminal_run(client: TestClient) -> None:
    with _ProviderServer("failure") as provider, override_allow_model_requests(True):
        auth = _login(client)
        _configure(client, auth, provider.base_url)
        response = _send(client, auth)
    assert response.status_code == 200
    database = client.app.state.database
    run = database.agent_runs.find_one({}, {"_id": 0})
    events = list(database.agent_thread_events.find({}, {"_id": 0}).sort("eventSeq", 1))
    assert run["status"] == "failed"
    assert run["error"] == "AI 服务暂不可用"
    assert events[-1]["type"] == "run.failed"
    assert database.ai_usage.count_documents({"token": {"$exists": True}}) == 0


QWEN_REASONING = "先核对资料区与选区"


def _thread_id(database) -> str:
    return database.agent_threads.find_one({}, {"id": 1})["id"]


def _stream_turn(client: TestClient, auth: dict, thread_id: str, text: str, message_id: str):
    return client.post(
        f"/api/cases/c-draft-1/agent/thread/{thread_id}/stream",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=_body(text, message_id),
    )


def _reasoning_text(message: dict) -> str:
    return "".join(
        part.get("text", "") for part in message.get("parts", [])
        if part.get("type") == "reasoning"
    )


def _assistant_messages(client: TestClient, database) -> list[dict]:
    snapshot = client.get(
        f"/api/cases/c-draft-1/agent/threads/{_thread_id(database)}"
    ).json()
    return [m for m in snapshot["messages"] if m["role"] == "assistant"]


def _configure_qwen(client: TestClient, auth: dict, provider) -> dict:
    _configure_model(client, auth, provider.base_url, "qwen-plus")
    return client.app.state.database


def test_qwen_plus_request_enables_official_thinking_parameter(
    client: TestClient,
) -> None:
    """qwen-plus：按官方协议经 enable_thinking 开启思考，真实 reasoning 流出。"""
    with _ProviderServer() as provider, override_allow_model_requests(True):
        auth = _login(client)
        database = _configure_qwen(client, auth, provider)
        response = _send(client, auth)
        assert response.status_code == 200
        assert '"type":"reasoning-start"' in response.text
        assert "先核对" in response.text and "资料区与选区" in response.text
        assert provider.server.seen[0]["enable_thinking"] is True
        message = database.agent_messages.find_one(
            {"role": "assistant"}, {"_id": 0, "parts": 1}
        )
        assert _reasoning_text(message) == QWEN_REASONING


def test_qwen_plus_history_keeps_reasoning_content_out_of_requests(
    client: TestClient,
) -> None:
    """官方多轮协议：历史消息只回传 content，不回传 reasoning_content。"""
    with _ProviderServer() as provider, override_allow_model_requests(True):
        auth = _login(client)
        database = _configure_qwen(client, auth, provider)
        assert _send(client, auth).status_code == 200
        followup = _stream_turn(
            client, auth, _thread_id(database), "追问一轮", "followup-message"
        )
        assert followup.status_code == 200
        assert provider.server.seen[1]["enable_thinking"] is True
        assert all(
            "reasoning_content" not in message
            for message in provider.server.seen[1]["messages"]
            if message.get("role") == "assistant"
        )


def test_qwen_plus_reasoning_replays_identically_in_history(
    client: TestClient,
) -> None:
    """历史回放与流式一致：每轮快照中的思考与 provider 真实返回一致。"""
    with _ProviderServer() as provider, override_allow_model_requests(True):
        auth = _login(client)
        database = _configure_qwen(client, auth, provider)
        assert _send(client, auth).status_code == 200
        followup = _stream_turn(
            client, auth, _thread_id(database), "追问一轮", "followup-message"
        )
        assert followup.status_code == 200
        messages = _assistant_messages(client, database)
        assert len(messages) == 2
        for message in messages:
            assert _reasoning_text(message) == QWEN_REASONING


def test_model_without_official_thinking_support_stays_untouched(
    client: TestClient,
) -> None:
    """非思考模型不下发思考参数，也不伪造思考内容。"""
    with _ProviderServer() as provider, override_allow_model_requests(True):
        auth = _login(client)
        _configure_model(client, auth, provider.base_url, "gpt-4o")
        response = _send(client, auth)
        assert response.status_code == 200
        assert "reasoning" not in response.text
        assert provider.server.seen[0].get("enable_thinking") is None
        database = client.app.state.database
        message = database.agent_messages.find_one(
            {"role": "assistant"}, {"_id": 0, "parts": 1}
        )
        assert all(part.get("type") != "reasoning" for part in message["parts"])
