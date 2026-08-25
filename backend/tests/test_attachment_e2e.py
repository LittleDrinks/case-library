from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from minio import Minio

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
pytestmark = pytest.mark.e2e(
    "CASE_LIBRARY_E2E_URL",
    "OBJECT_STORE_ENDPOINT",
    "OBJECT_STORE_BUCKET",
    "OBJECT_STORE_ACCESS_KEY_FILE",
    "OBJECT_STORE_SECRET_KEY_FILE",
)


def _secret(name: str) -> str:
    return Path(os.environ[name]).read_text(encoding="utf-8").strip()


def _store() -> tuple[Minio, str]:
    client = Minio(
        os.environ["OBJECT_STORE_ENDPOINT"],
        access_key=_secret("OBJECT_STORE_ACCESS_KEY_FILE"),
        secret_key=_secret("OBJECT_STORE_SECRET_KEY_FILE"),
        secure=False,
    )
    return client, os.environ["OBJECT_STORE_BUCKET"]


def _clear_bucket() -> None:
    store, bucket = _store()
    if not store.bucket_exists(bucket):
        return
    for item in store.list_objects(bucket, recursive=True):
        store.remove_object(bucket, item.object_name)


@pytest.fixture(autouse=True)
def clean_bucket():
    _clear_bucket()
    yield
    _clear_bucket()


def _login(username: str, password: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return client, response.json()["csrfToken"]


def _author_and_admin():
    return _login("user", "user123"), _login("admin", "admin123")


def _create_case(client: httpx.Client, csrf: str) -> dict:
    response = client.post(
        "/api/cases", headers={"X-CSRF-Token": csrf}, json={"title": "附件 E2E"}
    )
    assert response.status_code == 200
    return response.json()


def _revision(client: httpx.Client, case_id: str) -> int:
    return client.get(f"/api/cases/{case_id}").json()["revision"]


def _upload(client: httpx.Client, csrf: str, case_id: str, level: str) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/attachments",
        headers={"X-CSRF-Token": csrf},
        data={"accessLevel": level, "revision": _revision(client, case_id)},
        files={"file": (f"{level}.txt", level.encode(), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def _publish(author, author_csrf: str, admin, admin_csrf: str, case: dict) -> None:
    submitted = _submit(author, author_csrf, case)
    _approve(admin, admin_csrf, case["id"], submitted)


def _transition(client, csrf: str, case_id: str, body: dict) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers={"X-CSRF-Token": csrf},
        json=body,
    )
    assert response.status_code == 200
    return response.json()


def _submit(client, csrf: str, case: dict) -> dict:
    return _transition(
        client,
        csrf,
        case["id"],
        {"command": "submit", "revision": _revision(client, case["id"])},
    )


def _approve(admin, csrf: str, case_id: str, submitted: dict) -> dict:
    started = _transition(
        admin,
        csrf,
        case_id,
        {"command": "start", "revision": submitted["case"]["revision"]},
    )
    return _transition(
        admin,
        csrf,
        case_id,
        {
            "command": "approve",
            "revision": started["case"]["revision"],
            "submittedVersionId": submitted["version"]["id"],
        },
    )


def _assert_downloads(client, case_id: str, rows: list[dict], expected: list[int]):
    actual = [
        client.get(f"/api/cases/{case_id}/attachments/{row['id']}/content").status_code
        for row in rows
    ]
    assert actual == expected


def _delete(client, csrf: str, case_id: str, attachment_id: str) -> None:
    response = client.delete(
        f"/api/cases/{case_id}/attachments/{attachment_id}",
        headers={"X-CSRF-Token": csrf},
        params={"revision": _revision(client, case_id)},
    )
    assert response.status_code == 204


def _assert_admin_cannot_delete(admin, csrf: str, case_id: str, row: dict) -> None:
    response = admin.delete(
        f"/api/cases/{case_id}/attachments/{row['id']}",
        headers={"X-CSRF-Token": csrf},
        params={"revision": _revision(admin, case_id)},
    )
    assert response.status_code == 403


def _assert_published_permissions(case_id: str, rows: list[dict], admin) -> None:
    anonymous = httpx.Client(base_url=BASE_URL)
    assert len(anonymous.get(f"/api/cases/{case_id}/attachments").json()) == 3
    _assert_downloads(anonymous, case_id, rows, [200, 403, 403])
    blocked, _csrf = _login("10000001", "Demo-10000001-2026!")
    _assert_downloads(blocked, case_id, rows, [403, 403, 403])
    _assert_downloads(admin, case_id, rows, [200, 200, 200])


def _assert_campus_permissions(author, admin, admin_csrf: str) -> None:
    case = _create_case(admin, admin_csrf)
    rows = [
        _upload(admin, admin_csrf, case["id"], level)
        for level in ("public", "campus", "private")
    ]
    _publish(admin, admin_csrf, admin, admin_csrf, case)
    _assert_downloads(author, case["id"], rows, [200, 200, 403])


def _withdraw(client, csrf: str, case_id: str, submitted: dict) -> dict:
    return _transition(
        client,
        csrf,
        case_id,
        {"command": "withdraw", "revision": submitted["case"]["revision"]},
    )


def _snapshot(client, csrf: str, case_id: str) -> dict:
    return _transition(
        client,
        csrf,
        case_id,
        {"command": "snapshot", "revision": _revision(client, case_id)},
    )["snapshot"]


def _rollback(client, csrf: str, case_id: str, snapshot: dict) -> dict:
    return _transition(
        client,
        csrf,
        case_id,
        {
            "command": "rollback",
            "revision": _revision(client, case_id),
            "targetId": snapshot["id"],
        },
    )


def test_real_minio_attachment_permissions() -> None:
    author, author_csrf = _login("user", "user123")
    admin, admin_csrf = _login("admin", "admin123")
    case = _create_case(author, author_csrf)
    rows = [
        _upload(author, author_csrf, case["id"], level)
        for level in ("public", "campus", "private")
    ]
    assert admin.get(f"/api/cases/{case['id']}/attachments").status_code == 200
    _assert_admin_cannot_delete(admin, admin_csrf, case["id"], rows[0])
    _publish(author, author_csrf, admin, admin_csrf, case)
    _assert_published_permissions(case["id"], rows, admin)
    _assert_campus_permissions(author, admin, admin_csrf)


def test_versions_keep_their_attachment_snapshots() -> None:
    (author, csrf), (admin, admin_csrf) = _author_and_admin()
    case = _create_case(author, csrf)
    first_attachment = _upload(author, csrf, case["id"], "public")
    first = _submit(author, csrf, case)
    withdrawn = _withdraw(author, csrf, case["id"], first)
    delete_path = f"/api/cases/{case['id']}/attachments/{first_attachment['id']}"
    _delete(author, csrf, case["id"], first_attachment["id"])
    second_attachment = _upload(author, csrf, case["id"], "public")
    second = _submit(author, csrf, withdrawn["case"])
    _approve(admin, admin_csrf, case["id"], second)
    history = author.get(f"/api/cases/{case['id']}/history").json()
    assert [row["name"] for row in history["versions"][0]["attachments"]] == ["public.txt"]
    anonymous = httpx.Client(base_url=BASE_URL)
    assert anonymous.get(f"/api/cases/{case['id']}/attachments").json() == [second_attachment]
    version_path = f"{delete_path}/content?versionId={first['version']['id']}"
    assert author.get(version_path).content == b"public"
    assert anonymous.get(version_path).status_code == 404


def test_rollback_restores_the_snapshot_attachment_and_blob() -> None:
    author, csrf = _login("user", "user123")
    case = _create_case(author, csrf)
    attachment = _upload(author, csrf, case["id"], "private")
    snapshot = _snapshot(author, csrf, case["id"])
    path = f"/api/cases/{case['id']}/attachments/{attachment['id']}"
    _delete(author, csrf, case["id"], attachment["id"])
    assert (
        author.get(f"{path}/content?versionId={snapshot['id']}").content == b"private"
    )
    rolled = _rollback(author, csrf, case["id"], snapshot)
    assert rolled["case"]["revision"] == snapshot["sourceRevision"] + 2
    assert author.get(f"{path}/content").content == b"private"
