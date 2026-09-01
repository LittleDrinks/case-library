#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener

COOKIE_NAME = "case_library_session"
RUN_TIMEOUT_SECONDS = 120
RUN_POLL_SECONDS = 1


class SmokeError(Exception):
    pass


def request_json(
    opener,
    base_url: str,
    path: str,
    body: dict | None = None,
    cookie: str = "",
) -> tuple[object, str | None]:
    data = json.dumps(body, ensure_ascii=False).encode() if body else None
    headers = {"Content-Type": "application/json"} if data else {}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(base_url + path, data=data, headers=headers)
    try:
        with opener.open(request, timeout=30) as response:
            payload = json.load(response)
            set_cookie = response.headers.get("Set-Cookie")
    except (HTTPError, URLError, OSError, ValueError) as error:
        raise SmokeError("request") from error
    return payload, set_cookie


def session_cookie(header: str | None) -> str:
    parsed = SimpleCookie()
    parsed.load(header or "")
    value = parsed.get(COOKIE_NAME)
    if value is None:
        raise SmokeError("login")
    return f"{COOKIE_NAME}={value.value}"


def _chat_request(base_url: str, csrf_token: str, cookie: str, case_id: str, thread_id: str):
    body = {
        "id": "ai-smoke",
        "trigger": "submit-message",
        "messages": [{
            "id": "ai-smoke-message", "role": "user",
            "parts": [{"type": "text", "text": "只回复OK"}],
        }],
    }
    return Request(
        base_url + f"/api/cases/{quote(case_id, safe='')}/agent/thread/{quote(thread_id, safe='')}/stream",
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf_token,
            "Cookie": cookie,
        },
    )


def open_chat(opener, base_url: str, csrf_token: str, cookie: str, case_id: str, thread_id: str):
    try:
        return opener.open(_chat_request(base_url, csrf_token, cookie, case_id, thread_id), timeout=120)
    except (HTTPError, URLError, OSError) as error:
        raise SmokeError("chat request") from error


def drain_chat(response) -> None:
    try:
        # Drain transport bytes only; persisted Run status owns completion.
        response.read()
    except OSError as error:
        raise SmokeError("chat request") from error


def wait_for_run(opener, base_url: str, cookie: str, case_id: str, thread_id: str) -> None:
    path = f"/api/cases/{quote(case_id, safe='')}/agent/thread"
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshot, _header = request_json(opener, base_url, path, cookie=cookie)
        run = snapshot.get("latestRun") if isinstance(snapshot, dict) else None
        if isinstance(run, dict) and run.get("status") == "completed":
            return
        if isinstance(run, dict) and run.get("status") in {"failed", "cancelled"}:
            raise SmokeError("chat run")
        time.sleep(RUN_POLL_SECONDS)
    raise SmokeError("chat run")


def credentials() -> tuple[str, str]:
    username = os.environ.get("AI_SMOKE_USERNAME", "").strip()
    password = sys.stdin.readline().rstrip("\r\n")
    if not username or not password:
        raise SmokeError("credentials are required")
    return username, password


def login(opener, base_url: str, username: str, password: str) -> tuple[str, str]:
    print("AI smoke: login", flush=True)
    payload, cookie_header = request_json(
        opener,
        base_url,
        "/api/auth/login",
        {
            "username": username,
            "password": password,
        },
    )
    csrf_token = payload.get("csrfToken")
    if not isinstance(csrf_token, str) or not csrf_token:
        raise SmokeError("login")
    return csrf_token, session_cookie(cookie_header)


def require_settings(opener, base_url: str, cookie: str) -> None:
    print("AI smoke: settings", flush=True)
    settings, _header = request_json(
        opener,
        base_url,
        "/api/ai/settings",
        cookie=cookie,
    )
    if settings.get("configured") is not True:
        raise SmokeError("AI is not configured")


def select_thread(opener, base_url: str, cookie: str) -> tuple[str, str]:
    print("AI smoke: thread", flush=True)
    cases, _header = request_json(opener, base_url, "/api/cases?scope=mine", cookie=cookie)
    if not isinstance(cases, list):
        raise SmokeError("draft case")
    case = next((item for item in cases if item.get("workflowStatus") == "draft"), None)
    if not isinstance(case, dict) or not isinstance(case.get("id"), str):
        raise SmokeError("draft case")
    thread, _header = request_json(
        opener, base_url, f"/api/cases/{quote(case['id'], safe='')}/agent/thread", cookie=cookie
    )
    if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
        raise SmokeError("thread")
    return case["id"], thread["id"]


def run() -> None:
    base_url = os.environ.get("AI_SMOKE_APP_URL", "http://frontend").rstrip("/")
    username, password = credentials()
    opener = build_opener()
    csrf_token, cookie = login(opener, base_url, username, password)
    require_settings(opener, base_url, cookie)
    case_id, thread_id = select_thread(opener, base_url, cookie)
    print("AI smoke: chat", flush=True)
    with open_chat(opener, base_url, csrf_token, cookie, case_id, thread_id) as response:
        drain_chat(response)
    wait_for_run(opener, base_url, cookie, case_id, thread_id)
    print("AI smoke: passed", flush=True)


def main() -> int:
    try:
        run()
    except SmokeError as error:
        print(f"AI smoke failed: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("AI smoke failed: unexpected error", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
