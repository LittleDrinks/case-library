from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
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
        request = Request(f"{BASE_URL}{path}", payload, headers, method=method)
        response = opener.open(request)
        return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def login(username: str, password: str):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    status, body = request(
        opener, "POST", "/api/auth/login", {"username": username, "password": password}
    )
    assert status == 200
    return opener, body["csrfToken"]


def create_case(opener, csrf: str, title: str):
    document = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "教学案例正文"}]}],
    }
    status, case = request(
        opener, "POST", "/api/cases", {"title": title, "document": document}, csrf
    )
    assert status == 200
    return case


def _command(command: str, revision: int, **extra) -> dict:
    return {"command": command, "revision": revision, **extra}


def _assert_frozen_submission(opener, csrf: str, case: dict, result: dict) -> None:
    assert result["case"]["workflowStatus"] == "pending"
    assert result["version"]["id"] == result["case"]["submittedVersionId"]
    assert result["version"]["document"] == case["document"]
    history = request(opener, "GET", f"/api/cases/{case['id']}/history")[1]
    assert history["versions"] == [result["version"]]
    status, _body = request(
        opener,
        "PATCH",
        f"/api/cases/{case['id']}",
        {"title": "leak", "revision": result["case"]["revision"]},
        csrf,
    )
    assert status == 409


def test_owner_submit_freezes_an_immutable_version() -> None:
    opener, csrf = login("user", "user123")
    case = create_case(opener, csrf, f"lifecycle-{uuid.uuid4().hex}")
    result = submit_case(opener, csrf, case)
    _assert_frozen_submission(opener, csrf, case, result)


def submit_case(opener, csrf: str, case: dict) -> dict:
    status, result = request(
        opener,
        "POST",
        f"/api/cases/{case['id']}/lifecycle",
        {"command": "submit", "revision": case["revision"]},
        csrf,
    )
    assert status == 200
    return result


def transition(opener, csrf: str, case_id: str, body: dict):
    return request(opener, "POST", f"/api/cases/{case_id}/lifecycle", body, csrf)


def _transition_ok(opener, csrf: str, case_id: str, command: str, case: dict, **extra):
    status, result = transition(
        opener, csrf, case_id, _command(command, case["revision"], **extra)
    )
    assert status == 200
    return result


def _start_review(admin, csrf: str, case_id: str, submitted: dict) -> dict:
    started = _transition_ok(admin, csrf, case_id, "start", submitted["case"])
    assert started["case"]["workflowStatus"] == "reviewing"
    return started


def _approve(admin, csrf: str, case_id: str, started: dict, version_id: str) -> dict:
    return _transition_ok(
        admin,
        csrf,
        case_id,
        "approve",
        started["case"],
        submittedVersionId=version_id,
    )


def _assert_approved(approved: dict, submitted: dict) -> None:
    assert approved["case"]["workflowStatus"] == "published"
    assert approved["case"]["publicationStatus"] == "public"
    assert approved["case"]["publishedVersionId"] == submitted["version"]["id"]
    assert approved["case"]["submittedVersionId"] is None


def _hide(admin, csrf: str, case_id: str, case: dict) -> dict:
    return _transition_ok(admin, csrf, case_id, "hide", case)


def _restore(admin, csrf: str, case_id: str, case: dict) -> dict:
    return _transition_ok(admin, csrf, case_id, "restore", case)


def _withdraw(owner, csrf: str, case_id: str, case: dict) -> dict:
    return _transition_ok(owner, csrf, case_id, "withdraw", case)


def _transition_status(opener, csrf: str, case_id: str, command: str, revision: int):
    return transition(opener, csrf, case_id, _command(command, revision))[0]


def _submit_status(task) -> int:
    (opener, csrf), case = task
    return _transition_status(opener, csrf, case["id"], "submit", case["revision"])


def _concurrent_submit_statuses(case: dict, sessions: list[tuple]) -> list[int]:
    tasks = [(session, case) for session in sessions]
    with ThreadPoolExecutor(max_workers=2) as pool:
        return sorted(pool.map(_submit_status, tasks))


def _overwrite(owner, csrf: str, case_id: str, case: dict, target_id: str) -> dict:
    return _transition_ok(owner, csrf, case_id, "overwrite", case, targetId=target_id)


def assert_lifecycle_history(owner, case_id: str) -> None:
    history = request(owner, "GET", f"/api/cases/{case_id}/history")[1]
    assert [version["number"] for version in history["versions"]] == [1, 2]
    # 审核结论前撤回：首轮 submit→start 后作者 withdraw，再重投并重新开始审核。
    assert [event["action"] for event in history["events"]] == [
        "submit",
        "start",
        "withdraw",
        "submit",
        "start",
    ]


def test_admin_approves_only_the_started_submission_version() -> None:
    owner, owner_csrf = login("user", "user123")
    case = create_case(owner, owner_csrf, f"approval-{uuid.uuid4().hex}")
    submitted = submit_case(owner, owner_csrf, case)
    admin, admin_csrf = login("admin", "admin123")
    started = _start_review(admin, admin_csrf, case["id"], submitted)
    wrong = _command(
        "approve",
        started["case"]["revision"],
        submittedVersionId="cv-not-the-submitted-version",
    )
    assert transition(admin, admin_csrf, case["id"], wrong)[0] == 409
    approved = _approve(
        admin, admin_csrf, case["id"], started, submitted["version"]["id"]
    )
    _assert_approved(approved, submitted)


def publish_case(title: str):
    owner, owner_csrf = login("user", "user123")
    case = create_case(owner, owner_csrf, title)
    submitted = submit_case(owner, owner_csrf, case)
    admin, admin_csrf = login("admin", "admin123")
    started = _start_review(admin, admin_csrf, case["id"], submitted)
    approved = _approve(
        admin, admin_csrf, case["id"], started, submitted["version"]["id"]
    )
    return owner, case, submitted, approved


def test_anonymous_detail_reads_only_the_published_snapshot() -> None:
    owner, case, submitted, approved = publish_case(f"public-{uuid.uuid4().hex}")
    status, public = request(build_opener(), "GET", f"/api/cases/{case['id']}")
    assert status == 200
    assert public["document"] == submitted["version"]["document"]
    assert public["revision"] == submitted["version"]["sourceRevision"] == 1
    assert public["workflowStatus"] == "published"
    assert public["publicationStatus"] == "public"
    assert "ownerId" not in public and "submittedVersionId" not in public
    assert (
        request(owner, "GET", f"/api/cases/{case['id']}")[1]["revision"]
        == approved["case"]["revision"]
        == 4
    )


def test_admin_hides_and_restores_the_published_snapshot() -> None:
    _owner, case, submitted, approved = publish_case(f"hide-{uuid.uuid4().hex}")
    admin, csrf = login("admin", "admin123")
    hidden = _hide(admin, csrf, case["id"], approved["case"])
    assert hidden["case"]["publicationStatus"] == "hidden"
    assert request(build_opener(), "GET", f"/api/cases/{case['id']}")[0] == 404
    restored = _restore(admin, csrf, case["id"], hidden["case"])
    assert restored["case"]["publicationStatus"] == "public"
    public = request(build_opener(), "GET", f"/api/cases/{case['id']}")[1]
    assert public["document"] == submitted["version"]["document"]


def test_owner_reopens_only_a_hidden_published_case() -> None:
    owner, case, _submitted, approved = publish_case(f"reopen-{uuid.uuid4().hex}")
    admin, csrf = login("admin", "admin123")
    hidden = _hide(admin, csrf, case["id"], approved["case"])
    owner_csrf = request(owner, "GET", "/api/auth/session")[1]["csrfToken"]
    status, reopened = transition(
        owner, owner_csrf, case["id"], _command("reopen", hidden["case"]["revision"])
    )
    assert status == 200
    assert reopened["case"]["workflowStatus"] == "draft"
    assert reopened["case"]["publicationStatus"] == "hidden"
    edited = patch_case(owner, owner_csrf, reopened["case"], "重开后修改")
    assert edited["title"] == "重开后修改"
    assert request(build_opener(), "GET", f"/api/cases/{case['id']}")[0] == 404


def test_owner_withdraws_even_after_review_starts() -> None:
    owner, csrf = login("user", "user123")
    case = create_case(owner, csrf, f"withdraw-{uuid.uuid4().hex}")
    first = submit_case(owner, csrf, case)
    admin, admin_csrf = login("admin", "admin123")
    started = _start_review(admin, admin_csrf, case["id"], first)
    withdrawn = _withdraw(owner, csrf, case["id"], started["case"])
    assert withdrawn["case"]["workflowStatus"] == "draft"
    assert withdrawn["case"]["submittedVersionId"] is None
    stale = _command(
        "approve",
        started["case"]["revision"],
        submittedVersionId=started["case"]["submittedVersionId"],
    )
    assert transition(admin, admin_csrf, case["id"], stale)[0] == 409
    edited = patch_case(owner, csrf, withdrawn["case"], "撤回后修改")
    second = submit_case(owner, csrf, edited)
    _start_review(admin, admin_csrf, case["id"], second)
    assert_lifecycle_history(owner, case["id"])


def _race_withdraw_approve(
    owner, owner_csrf, admin, admin_csrf, case_id, revision, version_id
):
    with ThreadPoolExecutor(max_workers=2) as pool:
        withdraw = pool.submit(
            lambda: _transition_status(owner, owner_csrf, case_id, "withdraw", revision)
        )
        approve = pool.submit(
            lambda: transition(
                admin,
                admin_csrf,
                case_id,
                _command("approve", revision, submittedVersionId=version_id),
            )[0]
        )
        return sorted([withdraw.result(), approve.result()])


def test_withdraw_and_approve_admit_exactly_one_decision() -> None:
    owner, owner_csrf = login("user", "user123")
    case = create_case(owner, owner_csrf, f"race-{uuid.uuid4().hex}")
    submitted = submit_case(owner, owner_csrf, case)
    admin, admin_csrf = login("admin", "admin123")
    started = _start_review(admin, admin_csrf, case["id"], submitted)
    revision = started["case"]["revision"]
    version_id = submitted["version"]["id"]
    statuses = _race_withdraw_approve(
        owner, owner_csrf, admin, admin_csrf, case["id"], revision, version_id
    )
    assert statuses == [200, 409]
    _status, final = request(owner, "GET", f"/api/cases/{case['id']}")
    decided = final["workflowStatus"]
    assert decided == ("published" if final.get("publishedVersionId") else "draft")


def test_concurrent_submit_returns_one_conflict_instead_of_server_error() -> None:
    first, first_csrf = login("user", "user123")
    second, second_csrf = login("user", "user123")
    case = create_case(first, first_csrf, f"concurrent-{uuid.uuid4().hex}")
    sessions = [(first, first_csrf), (second, second_csrf)]
    statuses = _concurrent_submit_statuses(case, sessions)
    assert statuses == [200, 409]
    history = request(first, "GET", f"/api/cases/{case['id']}/history")[1]
    assert len(history["versions"]) == len(history["events"]) == 1


def test_non_owner_cannot_probe_case_revision_through_lifecycle() -> None:
    owner, csrf = login("user", "user123")
    case = create_case(owner, csrf, f"private-{uuid.uuid4().hex}")
    stranger, stranger_csrf = login("10000001", "Demo-10000001-2026!")
    revision = case["revision"] + 99
    assert (
        _transition_status(stranger, stranger_csrf, case["id"], "submit", revision)
        == 403
    )
    assert (
        _transition_status(stranger, stranger_csrf, case["id"], "overwrite", revision)
        == 403
    )


def patch_case(
    opener, csrf: str, case: dict, title: str,
    document: dict | None = None, steps: list[dict] | None = None,
) -> dict:
    body = {"title": title, "revision": case["revision"]}
    if document is not None:
        body.update({"document": document, "steps": steps})
    status, saved = request(
        opener,
        "PATCH",
        f"/api/cases/{case['id']}",
        body,
        csrf,
    )
    assert status == 200
    return saved


def _different_document_patch() -> tuple[dict, list[dict]]:
    text = "覆盖前的不同正文"
    document = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }
    steps = [{"stepType": "replace", "from": 1, "to": 1 + len("教学案例正文"),
              "slice": {"content": [{"type": "text", "text": text}]} }]
    return document, steps


def _assert_overwrite_history(history: dict, submitted: dict, changed: dict) -> None:
    versions = history["versions"]
    assert [row["number"] for row in versions] == [1, 2, 3]
    assert [row["kind"] for row in versions] == ["submission", "manual", "restore"]
    submission, baseline, restored = versions
    assert submission == submitted["version"]
    assert baseline["title"] == "恢复前的当前稿"
    assert baseline["document"] == changed["document"]
    assert baseline["sourceRevision"] == changed["revision"]
    assert restored["document"] == submitted["version"]["document"]
    assert restored["restoredFromId"] == submitted["version"]["id"]


def test_owner_overwrites_the_working_draft_with_a_submitted_version() -> None:
    owner, csrf = login("user", "user123")
    case = create_case(owner, csrf, f"overwrite-{uuid.uuid4().hex}")
    submitted = _transition_ok(owner, csrf, case["id"], "submit", case)
    withdrawn = _withdraw(owner, csrf, case["id"], submitted["case"])
    changed_document, steps = _different_document_patch()
    changed = patch_case(
        owner, csrf, withdrawn["case"], "覆盖后标题", changed_document, steps,
    )
    assert changed["document"] != submitted["version"]["document"]
    overwritten = _overwrite(owner, csrf, case["id"], changed, submitted["version"]["id"])

    assert overwritten["case"]["title"] == case["title"]
    assert overwritten["case"]["document"] == case["document"]
    assert submitted["version"]["document"] == case["document"]
    history = request(owner, "GET", f"/api/cases/{case['id']}/history")[1]
    _assert_overwrite_history(history, submitted, changed)
