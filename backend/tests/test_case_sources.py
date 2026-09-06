from __future__ import annotations

import io
from io import BytesIO
from zipfile import ZipFile

from docx import Document as open_docx
from fastapi.testclient import TestClient

from app.modules.auth.passwords import hash_password

CITATION = {"type": "citation", "attrs": {"sourceType": "case", "sourceId": ""}}


def login(client: TestClient, username: str = "user", password: str = "user123") -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def headers(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def revision(client: TestClient, case_id: str = "c-draft-1") -> int:
    return client.get(f"/api/cases/{case_id}").json()["revision"]


def make_user(client: TestClient, username: str, verified: bool) -> dict:
    client.app.state.database.users.insert_one(
        {
            "id": f"u-{username}",
            "username": username,
            "name": username,
            "password_hash": hash_password("Secret-pass1"),
            "role": "user",
            "status": "active",
            "must_change_password": False,
            "campus_verified": verified,
            "token_version": 0,
        }
    )
    return login(client, username, "Secret-pass1")


def cite_document(
    client: TestClient,
    auth: dict,
    marks: list[dict],
    case_id: str = "c-draft-1",
) -> object:
    nodes = [
        {"type": "text", "text": f"依据{index}", "marks": [mark]}
        for index, mark in enumerate(marks, start=1)
    ] or [{"type": "text", "text": "正文"}]
    document = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": nodes}],
    }
    return client.patch(
        f"/api/cases/{case_id}",
        headers=headers(auth),
        json={"document": document, "revision": revision(client, case_id)},
    )


def other_client(client: TestClient) -> TestClient:
    """同一应用上的独立会话，避免管理员 Cookie 影响读者请求。"""
    return TestClient(client.app)


def mount_source(client: TestClient, auth: dict, source_case_id: str, **extra) -> object:
    body = {"sourceCaseId": source_case_id, "revision": revision(client), **extra}
    return client.post(
        "/api/cases/c-draft-1/case-sources", headers=headers(auth), json=body
    )


def mount_material(client: TestClient, auth: dict, material_id: str) -> object:
    return client.post(
        "/api/cases/c-draft-1/materials",
        headers=headers(auth),
        json={"materialId": material_id, "revision": revision(client)},
    )


def upload_attachment(client: TestClient, auth: dict) -> dict:
    response = client.post(
        "/api/cases/c-draft-1/attachments",
        headers=headers(auth),
        files={"file": ("notes.txt", io.BytesIO(b"attach"), "text/plain")},
        data={"accessLevel": "public", "revision": str(revision(client))},
    )
    assert response.status_code == 201
    return response.json()


def test_mount_pins_the_current_published_version(client: TestClient) -> None:
    auth = login(client)
    published = client.get("/api/cases/c-02/public").json()
    response = mount_source(client, auth, "c-02")
    assert response.status_code == 201
    row = response.json()
    assert row["sourceType"] == "case"
    assert row["caseId"] == "c-02"
    assert row["versionId"] == published["publishedVersionId"]
    assert row["versionNumber"] >= 1


def test_mount_rejects_duplicate_or_invalid_sources(client: TestClient) -> None:
    auth = login(client)
    assert mount_source(client, auth, "c-02").status_code == 201
    assert mount_source(client, auth, "c-02").status_code == 409
    assert mount_source(client, auth, "c-draft-1").status_code == 409
    assert mount_source(client, auth, "c-pending-1").status_code == 409
    assert mount_source(client, auth, "c-missing").status_code == 404
    published = client.get("/api/cases/c-05/public").json()
    assert (
        mount_source(client, auth, "c-05", versionId="cv-not-real").status_code == 404
    )
    assert published["publishedVersionId"]


def test_citation_save_rejects_dangling_sources(client: TestClient) -> None:
    auth = login(client)
    dangling = {**CITATION, "attrs": {"sourceType": "case", "sourceId": "src-none"}}
    assert cite_document(client, auth, [dangling]).status_code == 422


def test_case_source_removal_blocked_while_cited(client: TestClient) -> None:
    auth = login(client)
    source_id = mount_source(client, auth, "c-02").json()["id"]
    mark = {**CITATION, "attrs": {"sourceType": "case", "sourceId": source_id}}
    assert cite_document(client, auth, [mark]).status_code == 200
    url = f"/api/cases/c-draft-1/case-sources/{source_id}"
    blocked = client.delete(url, params={"revision": revision(client)}, headers=headers(auth))
    assert blocked.status_code == 409
    assert cite_document(client, auth, []).status_code == 200
    removed = client.delete(
        url, params={"revision": revision(client)}, headers=headers(auth)
    )
    assert removed.status_code == 204


def _cited_marks(attachment_id: str) -> list[dict]:
    return [
        {"type": "citation", "attrs": {"sourceType": "material", "sourceId": "m-kcsz"}},
        {
            "type": "citation",
            "attrs": {"sourceType": "attachment", "sourceId": attachment_id},
        },
    ]


def test_material_and_attachment_removal_blocked_while_cited(client: TestClient) -> None:
    auth = login(client)
    assert mount_material(client, auth, "m-kcsz").status_code == 201
    attachment = upload_attachment(client, auth)
    assert cite_document(client, auth, _cited_marks(attachment["id"])).status_code == 200
    material = client.delete(
        "/api/cases/c-draft-1/materials/m-kcsz",
        params={"revision": revision(client)},
        headers=headers(auth),
    )
    attachment = client.delete(
        f"/api/cases/c-draft-1/attachments/{attachment['id']}",
        params={"revision": revision(client)},
        headers=headers(auth),
    )
    assert material.status_code == 409
    assert attachment.status_code == 409


def test_submit_freezes_case_sources(client: TestClient) -> None:
    auth = login(client)
    row = mount_source(client, auth, "c-02").json()
    assert cite_document(
        client,
        auth,
        [{**CITATION, "attrs": {"sourceType": "case", "sourceId": row["id"]}}],
    ).status_code == 200
    response = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json={"command": "submit", "revision": revision(client)},
    )
    assert response.status_code == 200
    version = response.json()["version"]
    assert version["caseSources"][0]["versionId"] == row["versionId"]


def test_sources_endpoint_orders_and_numbers_all_entries(client: TestClient) -> None:
    auth = login(client)
    assert mount_material(client, auth, "m-kcsz").status_code == 201
    source_id = mount_source(client, auth, "c-02").json()["id"]
    upload_attachment(client, auth)
    response = client.get("/api/cases/c-draft-1/sources")
    assert response.status_code == 200
    entries = response.json()["entries"]
    assert [entry["number"] for entry in entries] == list(range(1, len(entries) + 1))
    assert {entry["sourceType"] for entry in entries} == {
        "attachment",
        "material",
        "case",
    }
    case_entry = next(entry for entry in entries if entry["sourceType"] == "case")
    assert case_entry["id"] == source_id
    assert "/#/cases/c-02?versionId=" in case_entry["url"]
    assert case_entry["version"].startswith("v")


def test_sources_order_by_body_citations_and_pin_frozen_attachment_links(
    client: TestClient,
) -> None:
    auth = login(client)
    assert mount_material(client, auth, "m-kcsz").status_code == 201
    source_id = mount_source(client, auth, "c-02").json()["id"]
    cited_attachment = upload_attachment(client, auth)
    spare_attachment = upload_attachment(client, auth)
    assert (
        cite_document(
            client,
            auth,
            [
                {
                    "type": "citation",
                    "attrs": {
                        "sourceType": "attachment",
                        "sourceId": cited_attachment["id"],
                    },
                },
                {
                    "type": "citation",
                    "attrs": {"sourceType": "case", "sourceId": source_id},
                },
            ],
        ).status_code
        == 200
    )
    submitted = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json={"command": "submit", "revision": revision(client)},
    )
    assert submitted.status_code == 200
    version_id = submitted.json()["version"]["id"]

    live = client.get("/api/cases/c-draft-1/sources").json()["entries"]
    live_link = next(
        entry for entry in live if entry["id"] == cited_attachment["id"]
    )
    assert "?versionId" not in live_link["url"]

    frozen = client.get(
        "/api/cases/c-draft-1/sources", params={"versionId": version_id}
    ).json()["entries"]
    assert [entry["id"] for entry in frozen] == [
        cited_attachment["id"],
        source_id,
        "m-kcsz",
        spare_attachment["id"],
    ]
    assert [entry["number"] for entry in frozen] == [1, 2, 3, 4]
    link = next(
        entry for entry in frozen if entry["id"] == cited_attachment["id"]
    )
    assert link["url"].endswith(
        f"/api/cases/c-draft-1/attachments/{cited_attachment['id']}"
        f"/content?versionId={version_id}"
    )


def test_public_pinned_read_and_export_permissions(client: TestClient) -> None:
    login(client)
    admin_client = other_client(client)
    version_id = client.get("/api/cases/c-02/public").json()["publishedVersionId"]
    assert client.get(f"/api/cases/c-02/public?versionId={version_id}").status_code == 200
    sources = client.get(f"/api/cases/c-02/public?versionId={version_id}").json()[
        "sources"
    ]["entries"]
    assert all(entry["url"].startswith("http") for entry in sources)
    hide = admin_client.post(
        "/api/cases/c-02/lifecycle",
        headers=headers(login(admin_client, "admin", "admin123")),
        json={"command": "hide", "revision": revision(admin_client, "c-02")},
    )
    assert hide.status_code == 200
    assert client.get(f"/api/cases/c-02/public?versionId={version_id}").status_code == 404


def _edit_and_submit(client: TestClient, owner: dict, title: str) -> None:
    patched = client.patch(
        "/api/cases/c-draft-1",
        headers=headers(owner),
        json={"title": title, "revision": revision(client)},
    )
    assert patched.status_code == 200
    submitted = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(owner),
        json={"command": "submit", "revision": revision(client)},
    )
    assert submitted.status_code == 200


def _assert_campus_material(campus: dict, guest: dict, teacher: dict) -> None:
    from app.modules.materials.service import can_read_material

    assert can_read_material(campus, guest) is False
    assert can_read_material(campus, teacher) is True


def test_campus_material_requires_verified_identity(client: TestClient) -> None:
    login(client)
    owner_revision = revision(client)
    unverified = make_user(client, "guest-1", verified=False)
    verified = make_user(client, "teacher-1", verified=True)
    campus = {"accessLevel": "campus", "createdBy": "someone-else"}
    users = client.app.state.database.users
    guest = users.find_one({"id": unverified["user"]["id"]})
    teacher = users.find_one({"id": verified["user"]["id"]})
    _assert_campus_material(campus, guest, teacher)
    assert verified["user"]["campusVerified"] is True
    guest_client = other_client(client)
    guest_mount = guest_client.post(
        "/api/cases/c-draft-1/materials",
        headers=headers(login(guest_client, "guest-1", "Secret-pass1")),
        json={"materialId": "m-zrjs", "revision": owner_revision},
    )
    assert guest_mount.status_code == 404
    assert mount_material(client, login(client), "m-zrjs").status_code == 201


def test_case_source_reflects_offline_source_case(client: TestClient) -> None:
    auth = login(client)
    mount_source(client, auth, "c-05")
    admin_client = other_client(client)
    assert (
        admin_client.post(
            "/api/cases/c-05/lifecycle",
            headers=headers(login(admin_client, "admin", "admin123")),
            json={"command": "hide", "revision": revision(admin_client, "c-05")},
        ).status_code
        == 200
    )
    entries = client.get("/api/cases/c-draft-1/sources").json()["entries"]
    case_entry = next(entry for entry in entries if entry["sourceType"] == "case")
    assert case_entry["contentAvailable"] is False
    internal = admin_client.get("/api/cases/c-draft-1/sources").json()["entries"]
    assert next(e for e in internal if e["sourceType"] == "case")[
        "contentAvailable"
    ] is True


def _admin_command(client: TestClient, case_id: str, command: str) -> None:
    admin_client = other_client(client)
    response = admin_client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers=headers(login(admin_client, "admin", "admin123")),
        json={"command": command, "revision": revision(admin_client, case_id)},
    )
    assert response.status_code == 200, response.json()


def _approve_first_submission(client: TestClient, owner: dict, case_id: str) -> str:
    _submit_if_draft(client, owner, case_id)
    _admin_command(client, case_id, "start")
    return _admin_approve(client, case_id)


def _submit_if_draft(client: TestClient, owner: dict, case_id: str) -> None:
    detail = client.get(f"/api/cases/{case_id}").json()
    if detail["workflowStatus"] != "draft":
        return
    response = client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers=headers(owner),
        json={"command": "submit", "revision": revision(client, case_id)},
    )
    assert response.status_code == 200, response.json()


def _admin_approve(client: TestClient, case_id: str) -> str:
    admin_client = other_client(client)
    login(admin_client, "admin", "admin123")
    submitted = admin_client.get(f"/api/cases/{case_id}").json()["submittedVersionId"]
    approve = admin_client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers=headers(login(admin_client, "admin", "admin123")),
        json={
            "command": "approve",
            "revision": revision(admin_client, case_id),
            "submittedVersionId": submitted,
        },
    )
    assert approve.status_code == 200, approve.json()
    return client.get(f"/api/cases/{case_id}").json()["publishedVersionId"]


def _mount_case_version(
    client: TestClient, auth: dict, case_id: str, version_id: str | None
) -> object:
    body = {"sourceCaseId": "c-draft-1", "revision": revision(client, case_id)}
    if version_id:
        body["versionId"] = version_id
    return client.post(
        f"/api/cases/{case_id}/case-sources", headers=headers(auth), json=body
    )


def test_fixed_citations_read_old_approved_versions(client: TestClient) -> None:
    owner = login(client)
    v1 = _approve_first_submission(client, owner, "c-draft-1")
    _admin_command(client, "c-draft-1", "hide")
    _admin_command(client, "c-draft-1", "reopen")
    _edit_and_submit(client, owner, "第二版标题")
    pending = client.get("/api/cases/c-draft-1").json()["submittedVersionId"]
    new_case = client.post(
        "/api/cases", headers=headers(owner), json={"title": "引用方案例"}
    ).json()["id"]
    assert _mount_case_version(client, owner, new_case, pending).status_code == 409
    assert _anonymous_pinned(client, v1).status_code == 404
    v2 = _approve_first_submission(client, owner, "c-draft-1")
    _assert_pinned_historical(client, owner, new_case, v1, v2)


def _assert_pinned_historical(
    client: TestClient, owner: dict, new_case: str, v1: str, v2: str
) -> None:
    old_mount = _mount_case_version(client, owner, new_case, v1)
    assert old_mount.status_code == 201
    assert old_mount.json()["versionId"] == v1
    current_mount = _mount_case_version(client, owner, new_case, None)
    assert current_mount.status_code == 201
    assert current_mount.json()["versionId"] == v2
    pinned = _anonymous_pinned(client, v1)
    assert pinned.status_code == 200
    assert pinned.json()["versionId"] == v1
    assert isinstance(pinned.json()["sources"]["entries"], list)
    assert _anonymous_pinned(client, "cv-fake").status_code == 404


def _anonymous_pinned(client: TestClient, version_id: str) -> object:
    return other_client(client).get(
        f"/api/cases/c-draft-1/public?versionId={version_id}"
    )


def test_owner_export_docx_lists_all_retained_sources(client: TestClient) -> None:
    auth = login(client)
    assert mount_material(client, auth, "m-kcsz").status_code == 201
    mount_source(client, auth, "c-02")
    upload_attachment(client, auth)
    exported = client.get("/api/cases/c-draft-1/export.docx")
    assert exported.status_code == 200
    document = open_docx(BytesIO(exported.content))
    texts = [paragraph.text for paragraph in document.paragraphs]
    assert "参考资料" in texts
    assert sum(text.startswith("〔") for text in texts) == 3
    relations = _external_links(exported.content)
    assert any("/#/cases/c-02?versionId=" in url for url in relations)
    assert any("/api/materials/m-kcsz/content" in url for url in relations)


def _external_links(content: bytes) -> list[str]:
    with ZipFile(BytesIO(content)) as archive:
        rels = archive.read("word/_rels/document.xml.rels").decode("utf-8")
    return [
        part.split('"', 2)[1]
        for part in rels.split("Target=")
        if part.startswith('"http')
    ]
