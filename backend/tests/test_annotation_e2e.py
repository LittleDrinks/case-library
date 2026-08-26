from __future__ import annotations

import json
import os
import uuid
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
pytestmark = pytest.mark.e2e("CASE_LIBRARY_E2E_URL")


def request(opener, method: str, path: str, body=None, csrf: str = ""):
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    try:
        response = opener.open(
            Request(f"{BASE_URL}{path}", payload, headers, method=method)
        )
        return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def login(username: str, password: str):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    status, body = request(
        opener,
        "POST",
        "/api/auth/login",
        {
            "username": username,
            "password": password,
        },
    )
    assert status == 200
    return opener, body["csrfToken"]


def transition(opener, csrf: str, case: dict, command: str, **extra) -> dict:
    status, result = request(
        opener,
        "POST",
        f"/api/cases/{case['id']}/lifecycle",
        {
            "command": command,
            "revision": case["revision"],
            **extra,
        },
        csrf,
    )
    assert status == 200
    return result


def create_reviewing_case(owner, csrf: str) -> dict:
    marker = f"annotation-e2e-{uuid.uuid4().hex}"
    case = _create_case(owner, csrf, marker)
    return transition(owner, csrf, case, "submit")


def _create_case(owner, csrf: str, marker: str) -> dict:
    status, case = request(owner, "POST", "/api/cases", _selection(), csrf)
    assert status == 200
    status, saved = request(
        owner,
        "PATCH",
        f"/api/cases/{case['id']}",
        _changes(case, marker),
        csrf,
    )
    assert status == 200
    return saved


def _selection() -> dict:
    return {"stageId": "ug", "typeId": "ct-figure", "templateId": "tpl-general-v1"}


def _changes(case: dict, marker: str) -> dict:
    return {"title": marker, "document": _document(marker), "revision": case["revision"]}


def _document(marker: str) -> dict:
    heading = {
        "type": "heading",
        "attrs": {"level": 1},
        "content": [{"type": "text", "text": "一、教学说明"}],
    }
    paragraph = {"type": "paragraph", "content": [{"type": "text", "text": marker}]}
    return {"type": "doc", "content": [heading, paragraph]}


def _annotation_body(submitted: dict) -> dict:
    return {
        "quote": submitted["case"]["title"],
        "section": "一、教学说明",
        "content": "请补充可观察的评价标准。",
        "source": "admin",
    }


def annotate_and_reject(admin, csrf: str, submitted: dict) -> dict:
    case = transition(admin, csrf, submitted["case"], "start")["case"]
    annotation = _create_annotation(admin, csrf, case, submitted)
    returned = _reject_case(admin, csrf, case)
    assert returned["event"]["annotationIds"] == [annotation["id"]]
    return annotation


def _create_annotation(admin, csrf: str, case: dict, submitted: dict) -> dict:
    path = f"/api/cases/{case['id']}/annotations"
    status, annotation = request(admin, "POST", path, _annotation_body(submitted), csrf)
    assert status == 201
    return annotation


def _reject_case(admin, csrf: str, case: dict) -> dict:
    return transition(
        admin,
        csrf,
        case,
        "reject",
        submittedVersionId=case["submittedVersionId"],
        reasonType="教学目标不清晰",
    )


def resolve_as_owner(owner, csrf: str, case_id: str, annotation: dict) -> None:
    root = f"/api/cases/{case_id}/annotations/{annotation['id']}"
    status, _reply = request(
        owner,
        "POST",
        f"{root}/replies",
        {"content": "已补充。"},
        csrf,
    )
    assert status == 200
    status, resolved = request(
        owner,
        "PATCH",
        f"{root}/status",
        {"status": "resolved"},
        csrf,
    )
    assert status == 200 and resolved["status"] == "resolved"


def test_real_review_annotation_thread_survives_rejection() -> None:
    owner, owner_csrf = login("user", "user123")
    submitted = create_reviewing_case(owner, owner_csrf)
    admin, admin_csrf = login("admin", "admin123")
    annotation = annotate_and_reject(admin, admin_csrf, submitted)
    case_id = submitted["case"]["id"]
    status, rows = request(owner, "GET", f"/api/cases/{case_id}/annotations")
    assert status == 200 and rows == [annotation]
    resolve_as_owner(owner, owner_csrf, case_id, annotation)
