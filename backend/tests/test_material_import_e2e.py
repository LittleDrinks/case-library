from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from minio import Minio

BASE_URL = os.environ.get("CASE_LIBRARY_E2E_URL")
RAR_FIXTURE = Path("/app/fixtures/学习资料md.rar")
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


def _object_count() -> int:
    store, bucket = _store()
    return sum(1 for _item in store.list_objects(bucket, recursive=True))


@pytest.fixture(autouse=True)
def clean_bucket():
    _clear_bucket()
    yield
    _clear_bucket()


def _login(username: str, password: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=BASE_URL, timeout=180)
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return client, response.json()["csrfToken"]


def _import(
    client, csrf: str, files: list[tuple], access: str = "campus"
) -> httpx.Response:
    return client.post(
        "/api/admin/material-imports",
        headers={"X-CSRF-Token": csrf},
        data={"accessLevel": access},
        files=files,
    )


def _import_rar(client, csrf: str) -> httpx.Response:
    with RAR_FIXTURE.open("rb") as source:
        files = [("files", (RAR_FIXTURE.name, source, "application/vnd.rar"))]
        return _import(client, csrf, files)


def _assert_bad_item_isolated(response: httpx.Response) -> None:
    assert response.status_code == 201
    assert response.json()["status"] == "partial_success"
    assert [item["status"] for item in response.json()["items"]] == [
        "candidate",
        "failed",
    ]


def _assert_non_admin_denied(files: list[tuple]) -> None:
    teacher, csrf = _login("user", "user123")
    assert _import(teacher, csrf, files).status_code == 403
    response = httpx.post(f"{BASE_URL}/api/admin/material-imports", files=files)
    assert response.status_code == 401


def _approve(client, csrf: str, candidate_id: str) -> None:
    response = client.post(
        f"/api/admin/material-candidates/{candidate_id}/decision",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve"},
    )
    assert response.status_code == 200


def _import_approved(client, csrf: str, name: str, content: bytes, access: str) -> str:
    files = [("files", (name, content, "text/plain"))]
    response = _import(client, csrf, files, access)
    assert response.status_code == 201
    material_id = response.json()["items"][0]["candidateId"]
    _approve(client, csrf, material_id)
    return material_id


def test_real_rar_import_is_durable_and_idempotent() -> None:
    admin, csrf = _login("admin", "admin123")
    first = _import_rar(admin, csrf)
    assert first.status_code == 201
    assert first.json()["itemCount"] == 69
    assert len(first.json()["items"]) == 69
    assert {item["status"] for item in first.json()["items"]} == {"candidate"}
    assert _object_count() == 69

    second = _import_rar(admin, csrf)
    assert second.status_code == 201
    assert second.json()["itemCount"] == 69
    assert len(second.json()["items"]) == 69
    assert {item["status"] for item in second.json()["items"]} == {"duplicate"}
    assert _object_count() == 69
    assert (
        admin.get(f"/api/admin/material-imports/{second.json()['id']}").json()
        == second.json()
    )


def test_import_is_admin_only_and_isolates_bad_items() -> None:
    admin, csrf = _login("admin", "admin123")
    files = [
        ("files", ("valid.txt", b"valid", "text/plain")),
        ("files", ("broken.pdf", b"not-pdf", "application/pdf")),
    ]
    response = _import(admin, csrf, files)
    _assert_bad_item_isolated(response)
    _assert_non_admin_denied(files[:1])


def test_approved_material_downloads_original_bytes_with_access_control() -> None:
    marker = os.urandom(8).hex()
    admin, csrf = _login("admin", "admin123")
    public = _import_approved(
        admin, csrf, f"公开-{marker}.txt", b"public-original", "public"
    )
    campus = _import_approved(
        admin, csrf, f"校内-{marker}.txt", b"campus-original", "campus"
    )

    anonymous = httpx.Client(base_url=BASE_URL, timeout=180)
    assert (
        anonymous.get(f"/api/materials/{public}/content").content == b"public-original"
    )
    assert anonymous.get(f"/api/materials/{campus}/content").status_code == 404
    teacher, _csrf = _login("user", "user123")
    response = teacher.get(f"/api/materials/{campus}/content")
    assert (response.status_code, response.content) == (200, b"campus-original")
