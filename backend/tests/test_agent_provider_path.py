from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi.testclient import TestClient


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
        for text in ("生产", "模型回答"):
            chunk = _chunk(text)
            self.wfile.write(chunk)
            self.wfile.flush()


def _chunk(text: str) -> bytes:
    payload = {"choices": [{"index": 0, "delta": {"content": text}}]}
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
    response = client.put(
        "/api/ai/settings",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"mode": "custom", "baseUrl": base_url, "apiKey": "provider-key", "model": "model-a"},
    )
    assert response.status_code == 200


def _body(text: str) -> dict:
    return {
        "id": "browser-chat",
        "trigger": "submit-message",
        "messages": [{
            "id": "client-message", "role": "user",
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
    with _ProviderServer() as provider:
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
    with _ProviderServer("failure") as provider:
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
