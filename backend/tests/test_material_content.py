from __future__ import annotations

from urllib.parse import quote

from fastapi.testclient import TestClient


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def _import(client, auth: dict, filename: str, content: bytes, access: str) -> str:
    response = client.post(
        "/api/admin/material-imports",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        data={"accessLevel": access},
        files=[("files", (filename, content, "text/plain"))],
    )
    assert response.status_code == 201
    return response.json()["items"][0]["candidateId"]


def _approve(client: TestClient, auth: dict, candidate_id: str) -> None:
    response = client.post(
        f"/api/admin/material-candidates/{candidate_id}/decision",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"decision": "approve"},
    )
    assert response.status_code == 200


def _approved_material(
    client: TestClient, filename: str, content: bytes, access: str
) -> tuple[str, dict]:
    admin = _login(client, "admin", "admin123")
    material_id = _import(client, admin, filename, content, access)
    _approve(client, admin, material_id)
    return material_id, admin


def _logout(client: TestClient, auth: dict) -> None:
    response = client.post(
        "/api/auth/logout", headers={"X-CSRF-Token": auth["csrfToken"]}
    )
    assert response.status_code == 204


def test_anonymous_downloads_approved_public_material_bytes(client: TestClient) -> None:
    content = "公开素材原字节".encode()
    material_id, admin = _approved_material(
        client, "folder/教学资料.txt", content, "public"
    )
    _logout(client, admin)

    response = client.get(f"/api/materials/{material_id}/content")

    disposition = f"attachment; filename*=UTF-8''{quote('教学资料.txt', safe='')}"
    assert (response.status_code, response.content) == (200, content)
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"] == disposition
    assert material_id not in str(response.headers)


def test_campus_material_requires_login(client: TestClient) -> None:
    content = b"campus-only"
    material_id, admin = _approved_material(client, "campus.txt", content, "campus")
    _logout(client, admin)

    anonymous = client.get(f"/api/materials/{material_id}/content")
    _login(client, "user", "user123")
    teacher = client.get(f"/api/materials/{material_id}/content")

    assert anonymous.status_code == 404
    assert (teacher.status_code, teacher.content) == (200, content)


def test_private_material_is_hidden_from_other_users(client: TestClient) -> None:
    material_id, _admin = _approved_material(
        client, "private.txt", b"private", "private"
    )
    _login(client, "user", "user123")

    response = client.get(f"/api/materials/{material_id}/content")

    assert response.status_code == 404


def test_private_material_is_available_to_creator_and_admin(client: TestClient) -> None:
    content = b"creator-private"
    material_id, admin = _approved_material(client, "creator.txt", content, "private")
    database = client.app.state.database
    database.materials.update_one(
        {"id": material_id}, {"$set": {"createdBy": "u-user-demo"}}
    )

    assert client.get(f"/api/materials/{material_id}/content").content == content
    _logout(client, admin)
    _login(client, "user", "user123")
    assert client.get(f"/api/materials/{material_id}/content").content == content


def test_unapproved_and_inactive_materials_are_hidden(client: TestClient) -> None:
    admin = _login(client, "admin", "admin123")
    candidate_id = _import(client, admin, "candidate.txt", b"pending", "public")
    disabled_id, _admin = _approved_material(
        client, "disabled.txt", b"disabled", "public"
    )
    client.app.state.database.materials.update_one(
        {"id": disabled_id}, {"$set": {"status": "disabled"}}
    )

    candidate = client.get(f"/api/materials/{candidate_id}/content")
    disabled = client.get(f"/api/materials/{disabled_id}/content")

    assert (candidate.status_code, disabled.status_code) == (404, 404)


def test_material_detail_returns_content_metadata_without_storage_keys(
    client: TestClient,
) -> None:
    material_id, _admin = _approved_material(client, "detail.txt", b"detail", "public")
    response = client.get(f"/api/materials/{material_id}")

    body = response.json()
    assert response.status_code == 200
    assert body["title"] == "detail"
    assert body["contentAvailable"] is True
    assert body["downloadAvailable"] is True
    assert not {"blobId", "sha256", "createdBy", "provenance"} & body.keys()


def test_material_detail_and_download_hide_denied_inactive_and_missing_records(
    client: TestClient,
) -> None:
    private_id, admin = _approved_material(client, "private-detail.txt", b"private", "private")
    inactive_id, admin = _approved_material(client, "inactive-detail.txt", b"inactive", "public")
    client.app.state.database.materials.update_one(
        {"id": inactive_id}, {"$set": {"status": "disabled"}}
    )
    _logout(client, admin)
    _login(client, "user", "user123")

    detail = client.get(f"/api/materials/{private_id}")
    download = client.get(f"/api/materials/{private_id}/content")
    inactive = client.get(f"/api/materials/{inactive_id}")
    missing = client.get("/api/materials/not-a-material")
    assert {response.status_code for response in (detail, download, inactive, missing)} == {404}
