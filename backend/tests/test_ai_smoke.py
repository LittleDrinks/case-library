from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest


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
        if self.path == "/api/ai/settings":
            payload = {"configured": self.server.configured, "effectiveModel": "secret-model"}
        elif self.path == "/api/cases?scope=mine":
            payload = [{"id": "secret-case", "workflowStatus": "draft"}]
        else:
            payload = self._snapshot()
        self._json(payload)

    def _snapshot(self) -> dict:
        request_id = self.server.request_ids[-1] if self.server.request_ids else ""
        if not request_id:
            return self._record_snapshot({"id": "secret-thread", "messages": [], "activeRun": None, "latestRun": None})
        if self.server.stale_current and self.server.poll_count == 0:
            self.server.poll_count += 1
            return self._record_snapshot({
                "id": "secret-thread", "messages": [],
                "activeRun": {"id": "current-run", "status": "active", "clientRequestId": request_id},
                "latestRun": {"id": "stale-run", "status": "completed", "clientRequestId": "stale-request"},
            })
        self.server.poll_count += 1
        latest = None if self.server.run_status is None else {
            "id": "secret-run", "status": self.server.run_status, "clientRequestId": request_id,
        }
        return self._record_snapshot(
            {"id": "secret-thread", "messages": [], "activeRun": None, "latestRun": latest}
        )

    def _record_snapshot(self, payload: dict) -> dict:
        self.server.snapshots.append(payload)
        return payload

    def do_POST(self) -> None:
        body = self._body()
        self.server.seen.append((self.path, self.headers, body))
        if self.path == "/api/auth/login":
            self._json({"csrfToken": "secret-csrf", "user": {}}, cookie=True)
            return
        request_id = body["messages"][-1]["id"]
        if request_id in self.server.request_ids:
            self.send_response(409)
            self.end_headers()
            return
        self.server.request_ids.append(request_id)
        self._stream()

    def _stream(self) -> None:
        body = b"opaque response bytes"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


class SnapshotResponse:
    def __init__(self, payload: dict) -> None:
        self._stream = io.BytesIO(json.dumps(payload).encode())
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self._stream.close()

    def read(self, *args):
        return self._stream.read(*args)


class SnapshotOpener:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def open(self, *_args, **_kwargs):
        return SnapshotResponse(self.payload)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0

    def monotonic(self) -> int:
        return self.now

    def sleep(self, seconds: int) -> None:
        self.now += seconds


def smoke_script_module():
    spec = importlib.util.spec_from_file_location("ai_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def run_smoke(
    configured: bool = True, run_status: str | None = "completed", invocations: int = 1,
    stale_current: bool = False,
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    server.configured = configured
    server.run_status = run_status
    server.seen = []
    server.request_ids = []
    server.poll_count = 0
    server.stale_current = stale_current
    server.snapshots = []
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = [invoke(server.server_address[1]) for _ in range(invocations)]
    server.shutdown()
    thread.join()
    result = results[0] if invocations == 1 else results
    return result, server.seen, server.snapshots


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
    result, seen, snapshots = run_smoke()
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "AI smoke: login",
        "AI smoke: settings",
        "AI smoke: thread",
        "AI smoke: chat",
        "AI smoke: passed",
    ]
    assert not any(secret in combined_output(result) for secret in SECRETS)
    assert seen[0][2] == {"username": "smoke-admin", "password": "smoke-password"}
    request_id = seen[4][2]["messages"][0]["id"]
    assert uuid.UUID(request_id).version == 4
    assert seen[4][2]["messages"][0]["parts"][0]["text"] == "只回复OK"
    assert seen[4][1]["X-CSRF-Token"] == "secret-csrf"
    assert "case_library_session=secret-cookie" in seen[4][1]["Cookie"]
    assert seen[5][0] == "/api/cases/secret-case/agent/thread"
    assert snapshots[-1]["latestRun"]["clientRequestId"] == request_id


def test_ai_smoke_rejects_unconfigured_platform_without_disclosure() -> None:
    result, seen, _snapshots = run_smoke(configured=False)
    assert result.returncode == 1
    assert "AI smoke failed: AI is not configured" in result.stderr
    assert [request[0] for request in seen] == ["/api/auth/login", "/api/ai/settings"]
    assert not any(secret in combined_output(result) for secret in SECRETS)


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_ai_smoke_requires_persisted_successful_run(status: str) -> None:
    result, _seen, _snapshots = run_smoke(run_status=status)
    assert result.returncode == 1
    assert "AI smoke failed: chat run" in result.stderr
    assert "secret-response" not in combined_output(result)


def test_ai_smoke_rejects_stale_completion_for_current_active_submission() -> None:
    result, seen, snapshots = run_smoke(run_status="failed", stale_current=True)
    request_id = seen[4][2]["messages"][0]["id"]
    assert result.returncode == 1
    assert snapshots[1]["activeRun"]["clientRequestId"] == request_id
    assert snapshots[1]["latestRun"]["clientRequestId"] == "stale-request"


def test_ai_smoke_repeated_invocations_use_fresh_request_ids() -> None:
    results, seen, snapshots = run_smoke(invocations=2)
    bodies = [body for _path, _headers, body in seen if body and "messages" in body]
    request_ids = [body["messages"][0]["id"] for body in bodies]
    assert [result.returncode for result in results] == [0, 0]
    assert len(request_ids) == 2 and len(set(request_ids)) == 2
    assert all(uuid.UUID(request_id).version == 4 for request_id in request_ids)
    assert snapshots[1]["latestRun"]["clientRequestId"] == request_ids[0]
    assert snapshots[-1]["latestRun"]["clientRequestId"] == request_ids[-1]


@pytest.mark.parametrize("latest_run", [None, {"status": "active", "clientRequestId": "request-id"}])
def test_ai_smoke_times_out_without_matching_terminal_run(latest_run) -> None:
    smoke = smoke_script_module()
    clock = FakeClock()
    opener = SnapshotOpener({"latestRun": latest_run})
    patches = [
        patch.object(smoke, "RUN_TIMEOUT_SECONDS", 2),
        patch.object(smoke, "RUN_POLL_SECONDS", 1),
        patch.object(smoke.time, "monotonic", clock.monotonic),
        patch.object(smoke.time, "sleep", clock.sleep),
    ]
    with patches[0], patches[1], patches[2], patches[3], pytest.raises(smoke.SmokeError):
        smoke.wait_for_run(opener, "http://app", "cookie", "case", "thread", "request-id")
    assert clock.now == 2
