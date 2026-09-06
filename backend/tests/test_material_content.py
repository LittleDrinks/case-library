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


def test_public_material_detail_hides_storage_fields(client: TestClient) -> None:
    material_id, admin = _approved_material(client, "detail.txt", b"detail", "public")
    client.app.state.database.materials.update_one(
        {"id": material_id},
        {"$set": {
            "summary": "详情摘要", "source": "资料来源", "sourceUrl": "https://example.test/source",
            "authority": "original", "materialType": "政策文件", "collectedAt": "2026-08-26",
        }},
    )
    _logout(client, admin)

    response = client.get(f"/api/materials/{material_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == "详情摘要"
    assert payload["sourceUrl"] == "https://example.test/source"
    assert payload["materialType"] == "政策文件"
    assert payload["contentAvailable"] is payload["hasFile"] is True
    assert {"blobId", "sha256", "createdBy", "approvedBy", "provenance"}.isdisjoint(payload)


def test_material_detail_follows_content_permissions(client: TestClient) -> None:
    material_id, admin = _approved_material(client, "campus.txt", b"campus", "campus")
    _logout(client, admin)

    anonymous = client.get(f"/api/materials/{material_id}")
    _login(client, "user", "user123")
    teacher = client.get(f"/api/materials/{material_id}")

    assert (anonymous.status_code, teacher.status_code) == (404, 200)


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

    content = client.get(f"/api/materials/{material_id}/content")
    detail = client.get(f"/api/materials/{material_id}")

    assert (content.status_code, detail.status_code) == (404, 404)


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

    candidate = client.get(f"/api/materials/{candidate_id}")
    disabled = client.get(f"/api/materials/{disabled_id}")
    missing = client.get("/api/materials/not-found")

    assert (candidate.status_code, disabled.status_code, missing.status_code) == (404, 404, 404)
