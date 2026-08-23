from __future__ import annotations

import io
import stat
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.modules.materials.errors import MaterialImportError

UNSAFE_ENTRIES = [
    ("../escape.txt", b"escape"),
    ("/absolute.txt", b"absolute"),
    ("C:/drive.txt", b"drive"),
    ("nested.data", None),
    ("program.bin", b"\x7fELFpayload"),
    ("script.sh", b"echo unsafe"),
]


class FailingBlobStore:
    def put(self, *_args) -> None:
        raise RuntimeError("minio-secret-internal-detail")


def zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries:
            archive.writestr(name, payload)
    return buffer.getvalue()


def symlink_zip() -> bytes:
    buffer = io.BytesIO()
    link = zipfile.ZipInfo("shortcut")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("safe.txt", b"safe")
        archive.writestr(link, "safe.txt")
    return buffer.getvalue()


def special_zip(name: str, file_type: int) -> bytes:
    buffer = io.BytesIO()
    entry = zipfile.ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = (file_type | 0o777) << 16
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("safe.txt", b"safe")
        archive.writestr(entry, b"special")
    return buffer.getvalue()


def login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def submit_import(client: TestClient, auth: dict, files: list[tuple]) -> object:
    return client.post(
        "/api/admin/material-imports",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        files=files,
    )


def _file(name: str, payload, media_type: str) -> list[tuple]:
    return [("files", (name, payload, media_type))]


def _submit_one(client: TestClient, auth: dict, name: str, payload, media_type: str):
    return submit_import(client, auth, _file(name, payload, media_type))


def _archive_file(name: str, entry: str, payload: bytes) -> tuple:
    archive = zip_bytes([(entry, payload)])
    return "files", (name, archive, "application/zip")


def _fail_candidate_insert(_record) -> None:
    raise RuntimeError("mongo unavailable")


def test_admin_imports_files_as_durable_candidates(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    files = [
        ("files", ("教学说明.md", b"# teaching", "text/markdown")),
        ("files", ("阅读材料.txt", b"reading", "text/plain")),
    ]
    response = submit_import(client, auth, files)

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "succeeded"
    assert job["accessLevel"] == "campus"
    assert [item["filename"] for item in job["items"]] == [
        "教学说明.md",
        "阅读材料.txt",
    ]
    assert [item["status"] for item in job["items"]] == ["candidate", "candidate"]
    assert client.get(f"/api/admin/material-imports/{job['id']}").json() == job


def test_reimport_marks_exact_content_as_duplicate(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    first = _submit_one(
        client, auth, "原始名称.md", b"same material", "text/markdown"
    ).json()
    response = _submit_one(
        client, auth, "再次上传.md", b"same material", "text/markdown"
    )

    assert response.status_code == 201
    duplicate = response.json()["items"][0]
    assert duplicate["filename"] == "再次上传.md"
    assert duplicate["status"] == "duplicate"
    assert duplicate["duplicateOf"] == first["items"][0]["candidateId"]


def test_real_rar_creates_one_candidate_item_per_entry(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    fixture = Path("/app/fixtures/学习资料md.rar")
    with fixture.open("rb") as archive:
        response = submit_import(
            client,
            auth,
            [
                ("files", (fixture.name, archive, "application/vnd.rar")),
            ],
        )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "succeeded"
    assert job["itemCount"] == 69
    assert len(job["items"]) == 69
    assert all(item["status"] == "candidate" for item in job["items"])
    assert all(item["filename"] != fixture.name for item in job["items"])


def test_invalid_known_signature_only_fails_that_item(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    files = [
        ("files", ("good.txt", b"readable", "text/plain")),
        ("files", ("broken.pdf", b"not a pdf", "application/pdf")),
    ]
    response = submit_import(client, auth, files)

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "partial_success"
    assert [item["status"] for item in job["items"]] == ["candidate", "failed"]


def test_storage_failure_does_not_expose_internal_error(client: TestClient) -> None:
    client.app.state.blob_store = FailingBlobStore()
    auth = login(client, "admin", "admin123")
    response = submit_import(
        client,
        auth,
        [
            ("files", ("material.txt", b"content", "text/plain")),
        ],
    )

    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["status"] == "failed"
    assert item["error"] == "文件处理失败"


def test_docx_stays_one_material_instead_of_body_import(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    document = zip_bytes([("[Content_Types].xml", b"<Types />")])
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    response = _submit_one(client, auth, "reference.docx", document, media_type)

    assert response.status_code == 201
    job = response.json()
    assert job["itemCount"] == 1
    assert job["items"][0]["filename"] == "reference.docx"
    assert job["items"][0]["status"] == "candidate"


@pytest.mark.parametrize(("unsafe_name", "payload"), UNSAFE_ENTRIES)
def test_unsafe_entry_does_not_rollback_safe_entry(
    client: TestClient,
    unsafe_name: str,
    payload: bytes | None,
) -> None:
    auth = login(client, "admin", "admin123")
    payload = payload or zip_bytes([("inside.txt", b"inside")])
    archive = zip_bytes([("safe.txt", b"safe"), (unsafe_name, payload)])
    response = _submit_one(client, auth, "batch.zip", archive, "application/zip")

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "partial_success"
    assert [item["status"] for item in job["items"]] == ["candidate", "failed"]


def test_archive_symlink_is_failed_without_rollback(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    response = submit_import(
        client,
        auth,
        [
            ("files", ("links.zip", symlink_zip(), "application/zip")),
        ],
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "partial_success"
    assert [item["status"] for item in job["items"]] == ["candidate", "failed"]


def test_archive_device_is_failed_without_rollback(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    response = submit_import(
        client,
        auth,
        [
            (
                "files",
                ("devices.zip", special_zip("device", stat.S_IFCHR), "application/zip"),
            ),
        ],
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "partial_success"
    assert [item["status"] for item in job["items"]] == ["candidate", "failed"]


def test_archive_rejects_path_longer_than_255(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    archive = zip_bytes([("safe.txt", b"safe"), ("x" * 256, b"long")])
    response = submit_import(
        client,
        auth,
        [
            ("files", ("paths.zip", archive, "application/zip")),
        ],
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "partial_success"
    assert [item["status"] for item in job["items"]] == ["candidate", "failed"]


def test_archive_rejects_item_over_128_mib(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.materials.archive.MAX_ITEM_BYTES", 4)
    auth = login(client, "admin", "admin123")
    archive = zip_bytes([("too-large.txt", b"12345")])
    response = submit_import(
        client,
        auth,
        [
            ("files", ("large.zip", archive, "application/zip")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "归档内单个文件不能超过 128MiB"


def test_archive_rejects_more_than_500_items(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    archive = zip_bytes([(f"{index}.txt", b"") for index in range(501)])
    response = submit_import(
        client,
        auth,
        [
            ("files", ("many.zip", archive, "application/zip")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "单次导入最多 500 项"


def test_archive_counts_directories_toward_500_item_limit(
    client: TestClient,
) -> None:
    auth = login(client, "admin", "admin123")
    directories = [(f"directory-{index}/", b"") for index in range(501)]
    response = submit_import(
        client,
        auth,
        [
            ("files", ("directories.zip", zip_bytes(directories), "application/zip")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "单次导入最多 500 项"


def test_archive_budget_is_shared_across_the_request(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    directories = [(f"directory-{index}/", b"") for index in range(300)]
    archive = zip_bytes(directories)
    files = [
        ("files", ("first.zip", archive, "application/zip")),
        ("files", ("second.zip", archive, "application/zip")),
    ]

    response = submit_import(client, auth, files)

    assert response.status_code == 413
    assert response.json()["detail"] == "单次导入最多 500 项"


def test_multiple_archives_keep_distinct_entry_contents(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    files = [
        (
            "files",
            ("first.zip", zip_bytes([("first.txt", b"alpha")]), "application/zip"),
        ),
        (
            "files",
            ("second.zip", zip_bytes([("second.txt", b"bravo")]), "application/zip"),
        ),
    ]

    response = submit_import(client, auth, files)

    items = response.json()["items"]
    assert response.status_code == 201
    assert [item["filename"] for item in items] == ["first.txt", "second.txt"]
    assert [item["status"] for item in items] == ["candidate", "candidate"]
    assert items[0]["sha256"] != items[1]["sha256"]


def test_archive_rejects_compression_ratio_over_100(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    archive = zip_bytes([("zeros.bin", b"\0" * 256_000)])
    response = submit_import(
        client,
        auth,
        [
            ("files", ("bomb.zip", archive, "application/zip")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "归档压缩比不能超过 100"


def test_archive_rejects_unsafe_directory_path(client: TestClient) -> None:
    auth = login(client, "admin", "admin123")
    archive = zip_bytes([("../unsafe/", b"")])
    response = submit_import(
        client,
        auth,
        [
            ("files", ("directories.zip", archive, "application/zip")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "归档目录路径不安全"


def test_request_rejects_more_than_128_mib(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.materials.archive.MAX_REQUEST_BYTES", 4)
    auth = login(client, "admin", "admin123")
    response = submit_import(
        client,
        auth,
        [
            ("files", ("large.txt", b"12345", "text/plain")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "导入请求不能超过 128MiB"


def test_archive_rejects_expansion_over_1_gib(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.materials.archive.MAX_EXPANDED_BYTES", 4)
    auth = login(client, "admin", "admin123")
    archive = zip_bytes([("expanded.txt", b"12345")])
    response = submit_import(
        client,
        auth,
        [
            ("files", ("expanded.zip", archive, "application/zip")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "归档展开后不能超过 1GiB"


def test_batch_rejects_combined_archive_expansion_over_1_gib(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.modules.materials.archive.MAX_EXPANDED_BYTES", 8)
    auth = login(client, "admin", "admin123")
    files = [
        _archive_file("first.zip", "first.txt", b"12345"),
        _archive_file("second.zip", "second.txt", b"67890"),
    ]

    response = submit_import(client, auth, files)

    assert response.status_code == 413
    assert response.json()["detail"] == "归档展开后不能超过 1GiB"


def test_material_import_requires_an_admin(client: TestClient) -> None:
    files = [("files", ("material.txt", b"content", "text/plain"))]
    assert client.post("/api/admin/material-imports", files=files).status_code == 401

    auth = login(client, "user", "user123")
    assert submit_import(client, auth, files).status_code == 403


def test_forced_password_change_blocks_material_import(client: TestClient) -> None:
    auth = login(client, "10000002", "Demo-10000002-2026!")
    files = [("files", ("material.txt", b"content", "text/plain"))]

    response = submit_import(client, auth, files)

    assert response.status_code == 403
    assert response.json() == {"detail": "请先修改初始密码"}


def test_material_import_job_read_requires_an_admin(client: TestClient) -> None:
    admin = login(client, "admin", "admin123")
    job = submit_import(
        client,
        admin,
        [
            ("files", ("material.txt", b"content", "text/plain")),
        ],
    ).json()
    login(client, "user", "user123")

    assert client.get(f"/api/admin/material-imports/{job['id']}").status_code == 403
    client.cookies.clear()
    assert client.get(f"/api/admin/material-imports/{job['id']}").status_code == 401


def test_metadata_failure_keeps_canonical_blob_for_reconciliation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = client.app.state.database.material_candidates
    monkeypatch.setattr(candidates, "insert_one", _fail_candidate_insert)
    auth = login(client, "admin", "admin123")
    response = _submit_one(client, auth, "material.txt", b"content", "text/plain")

    assert response.json()["items"][0]["status"] == "failed"
    assert len(client.app.state.blob_store.objects) == 1
    assert candidates.count_documents({}) == 0


def test_material_import_error_string_is_public_detail() -> None:
    error = MaterialImportError(413, "公开错误")

    assert str(error) == "公开错误"
