from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
MONGODB_URI = os.environ.get("AUTH_QUERY_MONGODB_URI")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL", "AUTH_QUERY_MONGODB_URI")


def _request(opener, method: str, path: str, body=None, csrf: str = ""):
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    request = Request(f"{BASE_URL}{path}", payload, headers, method=method)
    try:
        with opener.open(request) as response:
            content = response.read()
            return response.status, json.loads(content) if content else None
    except HTTPError as error:
        content = error.read()
        return error.code, json.loads(content) if content else None


def _password() -> str:
    return f"Issue356-{uuid.uuid4().hex}!a"


def _register(username: str, password: str):
    return _request(
        build_opener(),
        "POST",
        "/api/auth/register",
        {"username": username, "password": password},
    )


def test_registered_user_can_save_and_submit_a_private_case() -> None:
    username = f"issue356-{uuid.uuid4().hex}"
    password = _password()
    status, registered = _register(username, password)

    assert status == 201
    assert registered["username"] == username
    assert registered["role"] == "user"
    assert registered["campusVerified"] is False
    if password in json.dumps(registered):
        raise AssertionError("registration response contains the submitted password")
    assert "password_hash" not in registered

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    status, login = _request(
        opener,
        "POST",
        "/api/auth/login",
        {"username": username, "password": password},
    )
    assert status == 200
    owner_id = login["user"]["id"]
    assert login["user"]["role"] == "user"
    assert login["user"]["campusVerified"] is False

    status, session = _request(opener, "GET", "/api/auth/session")
    assert status == 200
    assert session["user"]["id"] == owner_id

    status, draft = _request(
        opener,
        "POST",
        "/api/cases",
        {
            "title": f"Issue 356 draft {uuid.uuid4().hex}",
            "document": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "合成投稿正文"}],
                    }
                ],
            },
        },
        login["csrfToken"],
    )
    assert status == 200
    assert draft["ownerId"] == owner_id
    assert draft["workflowStatus"] == "draft"
    assert draft["publicationStatus"] == "none"

    status, persisted = _request(opener, "GET", f"/api/cases/{draft['id']}")
    assert status == 200
    assert persisted["ownerId"] == owner_id
    submitted_status, submitted = _request(
        opener,
        "POST",
        f"/api/cases/{draft['id']}/lifecycle",
        {"command": "submit", "revision": persisted["revision"]},
        login["csrfToken"],
    )
    assert submitted_status == 200
    assert submitted["case"]["ownerId"] == owner_id
    assert submitted["case"]["workflowStatus"] == "pending"
    assert submitted["case"]["publicationStatus"] == "none"


def test_registration_reports_duplicate_and_invalid_credentials() -> None:
    username = f"issue356-{uuid.uuid4().hex}"
    password = _password()

    status, _registered = _register(username, password)
    assert status == 201

    duplicate_status, duplicate = _register(username, password)
    assert duplicate_status == 409
    assert duplicate == {"detail": "用户名已存在"}

    weak_status, weak = _register(f"issue356-{uuid.uuid4().hex}", "short")
    assert weak_status == 422
    assert weak == {"detail": "密码至少 12 个字符"}

    blank_status, blank = _register("", password)
    assert blank_status == 422
    assert blank and blank.get("detail")

    extra_status, _extra = _request(
        build_opener(),
        "POST",
        "/api/auth/register",
        {
            "username": f"issue356-extra-{uuid.uuid4().hex}",
            "password": password,
            "name": "不接受的额外字段",
        },
    )
    assert extra_status == 422


def test_concurrent_registration_keeps_one_username_in_real_mongodb() -> None:
    username = f"issue356-race-{uuid.uuid4().hex}"
    password = _password()
    gate = Barrier(2)

    def attempt():
        gate.wait()
        return _register(username, password)[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _index: attempt(), range(2)))

    assert statuses == [201, 409]
    mongo = MongoClient(MONGODB_URI)
    try:
        count = mongo.get_default_database().users.count_documents(
            {"username": username}
        )
    finally:
        mongo.close()
    assert count == 1
