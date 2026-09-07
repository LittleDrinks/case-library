from __future__ import annotations

import io

from fastapi.testclient import TestClient

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


def other_client(client: TestClient) -> TestClient:
    """同一应用上的独立会话，避免管理员 Cookie 影响读者请求。"""
    return TestClient(client.app)


def mount_source(client: TestClient, auth: dict, source_case_id: str, **extra) -> object:
    body = {"sourceCaseId": source_case_id, "revision": revision(client), **extra}
    return client.post(
        "/api/cases/c-draft-1/case-sources", headers=headers(auth), json=body
    )


def upload_attachment(client: TestClient, auth: dict, access: str = "public") -> dict:
    response = client.post(
        "/api/cases/c-draft-1/attachments",
        headers=headers(auth),
        files={"file": ("notes.txt", io.BytesIO(b"attach"), "text/plain")},
        data={"accessLevel": access, "revision": str(revision(client))},
    )
    assert response.status_code == 201
    return response.json()


def cite_document(client: TestClient, auth: dict, marks: list[dict]) -> object:
    nodes = [
        {"type": "text", "text": f"依据{index}", "marks": [mark]}
        for index, mark in enumerate(marks, start=1)
    ] or [{"type": "text", "text": "正文"}]
    document = {"type": "doc", "content": [{"type": "paragraph", "content": nodes}]}
    return client.patch(
        "/api/cases/c-draft-1",
        headers=headers(auth),
        json={"document": document, "revision": revision(client)},
    )


def mount_material(client: TestClient, auth: dict) -> object:
    return client.post(
        "/api/cases/c-draft-1/materials",
        headers=headers(auth),
        json={"materialId": "m-kcsz", "revision": revision(client)},
    )


def cited_marks(source_id: str, attachment_id: str) -> list[dict]:
    return [
        {**CITATION, "attrs": {"sourceType": "case", "sourceId": source_id}},
        {**CITATION, "attrs": {"sourceType": "material", "sourceId": "m-kcsz"}},
        {**CITATION, "attrs": {"sourceType": "attachment", "sourceId": attachment_id}},
    ]


def delete_source(client: TestClient, auth: dict, path: str) -> object:
    return client.delete(
        path, params={"revision": revision(client)}, headers=headers(auth)
    )


def submit_case(client: TestClient, auth: dict) -> str:
    response = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json={"command": "submit", "revision": revision(client)},
    )
    assert response.status_code == 200
    return response.json()["version"]["id"]


def ordered_source_fixture(client: TestClient, auth: dict) -> tuple[dict, dict, dict]:
    assert mount_material(client, auth).status_code == 201
    source = mount_source(client, auth, "c-02").json()
    cited, spare = upload_attachment(client, auth), upload_attachment(client, auth)
    marks = [
        {**CITATION, "attrs": {"sourceType": "attachment", "sourceId": cited["id"]}},
        {**CITATION, "attrs": {"sourceType": "case", "sourceId": source["id"]}},
    ]
    assert cite_document(client, auth, marks).status_code == 200
    return source, cited, spare


def _admin_command(client: TestClient, case_id: str, command: str, **extra) -> object:
    admin, admin_auth = _admin_session(client)
    body = {"command": command, "revision": revision(admin, case_id), **extra}
    response = admin.post(
        f"/api/cases/{case_id}/lifecycle", headers=headers(admin_auth), json=body,
    )
    assert response.status_code == 200, response.json()
    return response


def _admin_session(client: TestClient) -> tuple[TestClient, dict]:
    admin = other_client(client)
    return admin, login(admin, "admin", "admin123")


def _published_source(client: TestClient, owner: dict, title: str) -> str:
    """走真实提审流创建已发布来源案例，保证 approve 事件存在。"""
    created = client.post("/api/cases", headers=headers(owner), json={"title": title})
    assert created.status_code == 200
    case_id = created.json()["id"]
    _submit_and_approve(client, owner, case_id)
    return case_id


def _submit_and_approve(client: TestClient, owner: dict, case_id: str) -> str:
    submitted = client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers=headers(owner),
        json={"command": "submit", "revision": revision(client, case_id)},
    )
    assert submitted.status_code == 200, submitted.json()
    version_id = submitted.json()["version"]["id"]
    _admin_command(client, case_id, "start")
    _admin_command(client, case_id, "approve", submittedVersionId=version_id)
    return version_id


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
    assert "/#/cases/c-02?versionId=" in row["sourceUrl"]


def test_mount_rejects_duplicate_or_invalid_sources(client: TestClient) -> None:
    auth = login(client)
    assert mount_source(client, auth, "c-02").status_code == 201
    assert mount_source(client, auth, "c-02").status_code == 409
    assert mount_source(client, auth, "c-draft-1").status_code == 409
    assert mount_source(client, auth, "c-pending-1").status_code == 409
    assert mount_source(client, auth, "c-missing").status_code == 404
    assert mount_source(client, auth, "c-05", versionId="cv-not-real").status_code == 404


def test_mount_rejects_unapproved_versions_and_snapshots(client: TestClient) -> None:
    auth = login(client)
    database = client.app.state.database
    database.case_versions.insert_one(
        {"id": "cv-unapproved", "caseId": "c-02", "number": 9, "title": "未批准"}
    )
    pending = mount_source(client, auth, "c-02", versionId="cv-unapproved")
    assert pending.status_code == 404
    snap = _snapshot_id(client, auth)
    assert mount_source(client, auth, "c-02", versionId=snap).status_code == 404


def test_removal_requires_owner_and_editable_draft(client: TestClient) -> None:
    auth = login(client)
    source_id = mount_source(client, auth, "c-02").json()["id"]
    stranger = other_client(client)
    stranger_auth = login(stranger, "admin", "admin123")
    url = f"/api/cases/c-draft-1/case-sources/{source_id}"
    blocked = stranger.delete(
        url, params={"revision": revision(stranger)}, headers=headers(stranger_auth),
    )
    assert blocked.status_code == 403
    removed = client.delete(
        url, params={"revision": revision(client)}, headers=headers(auth)
    )
    assert removed.status_code == 204
    assert client.get("/api/cases/c-draft-1/case-sources").json() == []


def test_citation_save_rejects_dangling_sources(client: TestClient) -> None:
    auth = login(client)
    mark = {**CITATION, "attrs": {"sourceType": "case", "sourceId": "src-none"}}
    assert cite_document(client, auth, [mark]).status_code == 422


def test_cited_sources_cannot_be_removed(client: TestClient) -> None:
    auth = login(client)
    source = mount_source(client, auth, "c-02").json()
    material = mount_material(client, auth)
    attachment = upload_attachment(client, auth)
    assert material.status_code == 201
    assert cite_document(client, auth, cited_marks(source["id"], attachment["id"])).status_code == 200
    paths = [
        f"/api/cases/c-draft-1/case-sources/{source['id']}",
        "/api/cases/c-draft-1/materials/m-kcsz",
        f"/api/cases/c-draft-1/attachments/{attachment['id']}",
    ]
    assert [delete_source(client, auth, path).status_code for path in paths] == [409] * 3


def test_submit_freezes_case_sources(client: TestClient) -> None:
    auth = login(client)
    row = mount_source(client, auth, "c-02").json()
    response = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json={"command": "submit", "revision": revision(client)},
    )
    assert response.status_code == 200
    version = response.json()["version"]
    assert version["caseSources"][0]["versionId"] == row["versionId"]
    assert version["caseSources"][0]["versionNumber"] == row["versionNumber"]


def test_sources_endpoint_lists_and_numbers_all_entries(client: TestClient) -> None:
    auth = login(client)
    mount_source(client, auth, "c-02")
    upload_attachment(client, auth)
    entries = client.get("/api/cases/c-draft-1/sources").json()["entries"]
    assert [entry["number"] for entry in entries] == list(range(1, len(entries) + 1))
    assert {entry["sourceType"] for entry in entries} == {"attachment", "case"}
    case_entry = next(entry for entry in entries if entry["sourceType"] == "case")
    assert case_entry["url"].startswith("http")
    assert "/#/cases/c-02?versionId=" in case_entry["url"]
    assert case_entry["version"].startswith("v")
    attachment = next(entry for entry in entries if entry["sourceType"] == "attachment")
    assert "/attachments/" in attachment["url"]


def test_sources_order_by_first_body_citation_and_pin_frozen_links(
    client: TestClient,
) -> None:
    auth = login(client)
    source, cited, spare = ordered_source_fixture(client, auth)
    entries = client.get("/api/cases/c-draft-1/sources").json()["entries"]
    assert [entry["id"] for entry in entries] == [
        cited["id"], source["id"], "m-kcsz", spare["id"]
    ]
    assert [entry["number"] for entry in entries] == [1, 2, 3, 4]
    version_id = submit_case(client, auth)
    frozen = client.get(
        "/api/cases/c-draft-1/sources", params={"versionId": version_id}
    ).json()["entries"]
    frozen_cited = next(entry for entry in frozen if entry["id"] == cited["id"])
    assert frozen_cited["url"].endswith(
        f"/api/cases/c-draft-1/attachments/{cited['id']}/content?versionId={version_id}"
    )


def test_offline_source_case_keeps_entry_but_locks_content(client: TestClient) -> None:
    auth = login(client)
    mount_source(client, auth, "c-05")
    _admin_command(client, "c-05", "hide")
    sources = client.get("/api/cases/c-draft-1/case-sources").json()
    assert len(sources) == 1
    assert sources[0]["contentAvailable"] is False
    admin, admin_auth = _admin_session(client)
    admin_sources = admin.get(
        "/api/cases/c-draft-1/case-sources", headers=headers(admin_auth)
    ).json()
    assert admin_sources[0]["contentAvailable"] is True


def test_published_sources_visible_but_unauthorized_links_locked(
    client: TestClient,
) -> None:
    auth = login(client)
    mount_source(client, auth, "c-02")
    private = upload_attachment(client, auth, "private")
    _submit_and_approve(client, auth, "c-draft-1")
    reader = other_client(client)
    entries = reader.get("/api/cases/c-draft-1/sources").json()["entries"]
    by_type = {entry["sourceType"]: entry for entry in entries}
    assert by_type["case"]["contentAvailable"] is True
    assert by_type["attachment"]["contentAvailable"] is False
    denied = reader.get(
        f"/api/cases/c-draft-1/attachments/{private['id']}/content"
    )
    assert denied.status_code == 403


def test_source_version_does_not_drift_on_republish(client: TestClient) -> None:
    auth = login(client)
    source_id = _published_source(client, auth, "来源案例甲")
    mounted = mount_source(client, auth, source_id).json()
    v1 = mounted["versionId"]
    _admin_command(client, source_id, "hide")
    _admin_command(client, source_id, "reopen")
    _submit_and_approve(client, auth, source_id)
    sources = client.get("/api/cases/c-draft-1/case-sources").json()
    assert [row["versionNumber"] for row in sources] == [1]
    assert sources[0]["versionId"] == v1
    assert sources[0]["contentAvailable"] is True
    reader = other_client(client)
    pinned = reader.get(f"/api/cases/{source_id}/public", params={"versionId": v1})
    assert pinned.status_code == 200
    assert pinned.json()["publishedVersionId"] == v1
    assert pinned.json()["title"] == "来源案例甲"
    current = reader.get(f"/api/cases/{source_id}/public").json()["publishedVersionId"]
    assert current != v1


def test_mount_allows_approved_historical_version(client: TestClient) -> None:
    auth = login(client)
    source_id = _published_source(client, auth, "来源案例乙")
    v1 = client.get(f"/api/cases/{source_id}").json()["publishedVersionId"]
    _admin_command(client, source_id, "hide")
    _admin_command(client, source_id, "reopen")
    _submit_and_approve(client, auth, source_id)
    historical = mount_source(client, auth, source_id, versionId=v1)
    assert historical.status_code == 201
    assert historical.json()["versionNumber"] == 1
    latest = mount_source(client, auth, source_id)
    assert latest.status_code == 201
    assert latest.json()["versionNumber"] == 2


def _snapshot_id(client: TestClient, auth: dict) -> str:
    response = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json={"command": "snapshot", "revision": revision(client)},
    )
    return response.json()["snapshot"]["id"]


def test_public_pinned_read_rejects_unapproved_and_offline(client: TestClient) -> None:
    auth = login(client)
    mounted = mount_source(client, auth, "c-02").json()
    _admin_command(client, "c-02", "hide")
    reader = other_client(client)
    offline = reader.get(
        "/api/cases/c-02/public", params={"versionId": mounted["versionId"]}
    )
    assert offline.status_code == 404
    _admin_command(client, "c-02", "restore")
    snap = _snapshot_id(client, auth)
    assert reader.get(
        "/api/cases/c-02/public", params={"versionId": snap}
    ).status_code == 404
    assert reader.get(
        "/api/cases/c-draft-1/public", params={"versionId": snap}
    ).status_code == 404


def test_mount_defaults_to_newest_published_version_after_republish(
    client: TestClient,
) -> None:
    _admin_command(client, "c-02", "hide")
    _admin_command(client, "c-02", "reopen")
    admin, admin_auth = _admin_session(client)
    _submit_and_approve(admin, admin_auth, "c-02")
    current = client.get("/api/cases/c-02/public").json()["publishedVersionId"]
    mounted = mount_source(client, login(client), "c-02").json()
    assert mounted["versionId"] == current
    assert mounted["versionNumber"] == 2
