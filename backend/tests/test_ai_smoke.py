from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


SCRIPT = Path(__file__).parents[2] / "scripts" / "ai_smoke.py"
SECRETS = (
    "secret-base-url",
    "secret-key",
    "secret-model",
    "secret-response",
    "smoke-password",
    "secret-csrf",
    "secret-cookie",
    "只回复OK",
)


class SmokeHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *args):
        return

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def _json(self, payload: dict, cookie: bool = False) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie:
            self.send_header(
                "Set-Cookie",
                "case_library_session=secret-cookie; Path=/; HttpOnly; Secure",
            )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self.server.seen.append((self.path, self.headers, None))
        payload = {"configured": self.server.configured, "baseUrl": "secret-base-url"}
        payload.update({"effectiveModel": "secret-model", "apiKey": "secret-key"})
        self._json(payload)

    def do_POST(self) -> None:
        body = self._body()
        self.server.seen.append((self.path, self.headers, body))
        if self.path == "/api/auth/login":
            self._json({"csrfToken": "secret-csrf", "user": {}}, cookie=True)
            return
        self._stream()

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b'event: token\ndata: {"text":"secret-response"}\n\n')
        if self.server.complete_stream:
            self.wfile.write(b"event: done\ndata: {}\n\n")


def run_smoke(configured: bool = True, complete_stream: bool = True):
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    server.configured = configured
    server.complete_stream = complete_stream
    server.seen = []
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    result = invoke(server.server_address[1])
    server.shutdown()
    thread.join()
    return result, server.seen


def invoke(port: int):
    environment = {"PATH": os.environ["PATH"], "AI_SMOKE_USERNAME": "smoke-admin"}
    environment["AI_SMOKE_APP_URL"] = f"http://127.0.0.1:{port}"
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="smoke-password\n",
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def combined_output(result) -> str:
    return result.stdout + result.stderr


def test_ai_smoke_completes_without_disclosing_sensitive_values() -> None:
    result, seen = run_smoke()
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "AI smoke: login",
        "AI smoke: settings",
        "AI smoke: chat",
        "AI smoke: passed",
    ]
    assert not any(secret in combined_output(result) for secret in SECRETS)
    assert seen[0][2] == {"username": "smoke-admin", "password": "smoke-password"}
    assert seen[2][2] == {"messages": [{"role": "user", "content": "只回复OK"}]}
    assert seen[2][1]["X-CSRF-Token"] == "secret-csrf"
    assert "case_library_session=secret-cookie" in seen[2][1]["Cookie"]


def test_ai_smoke_rejects_unconfigured_platform_without_disclosure() -> None:
    result, seen = run_smoke(configured=False)
    assert result.returncode == 1
    assert "AI smoke failed: AI is not configured" in result.stderr
    assert [request[0] for request in seen] == ["/api/auth/login", "/api/ai/settings"]
    assert not any(secret in combined_output(result) for secret in SECRETS)


def test_ai_smoke_requires_terminal_stream_event() -> None:
    result, _seen = run_smoke(complete_stream=False)
    assert result.returncode == 1
    assert "AI smoke failed: chat stream" in result.stderr
    assert "secret-response" not in combined_output(result)
