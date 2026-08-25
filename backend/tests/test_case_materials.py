from __future__ import annotations

from fastapi.testclient import TestClient


def login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200
    return response.json()


def current_revision(client: TestClient) -> int:
    return client.get("/api/cases/c-draft-1").json()["revision"]


def headers(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def outbox_sequence(client: TestClient, logical_key: str) -> int:
    row = client.app.state.database.search_outbox.find_one({"_id": logical_key})
    return row["sequence"]


def revocation(client: TestClient, logical_key: str) -> dict | None:
    return client.app.state.database.search_revocations.find_one(
        {"logicalKey": logical_key}
    )


def assert_published_events(client, material_id: str) -> int:
    sequence = outbox_sequence(client, "case:c-draft-1")
    assert outbox_sequence(client, f"material:{material_id}") == sequence
    return sequence


def assert_hidden_events(client, material_id: str, previous: int) -> int:
    sequence = outbox_sequence(client, "case:c-draft-1")
    assert sequence > previous
    assert revocation(client, "case:c-draft-1")["sequence"] == sequence
    assert revocation(client, f"material:{material_id}")["sequence"] == sequence
    return sequence


def mount(client: TestClient, auth: dict, material_id: str) -> dict:
    response = client.post(
        "/api/cases/c-draft-1/materials",
        headers=headers(auth),
        json={"materialId": material_id, "revision": current_revision(client)},
    )
    assert response.status_code == 201
    return response.json()


def transition(client: TestClient, auth: dict, command: str, **extra) -> dict:
    body = {"command": command, "revision": current_revision(client), **extra}
    response = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json=body,
    )
    assert response.status_code == 200
    return response.json()


def unmount(client: TestClient, auth: dict, material_id: str) -> None:
    response = client.delete(
        f"/api/cases/c-draft-1/materials/{material_id}",
        headers=headers(auth),
        params={"revision": current_revision(client)},
    )
    assert response.status_code == 204


def seed_private_material(client, material_id, title, source, authority, owner) -> None:
    record = _private_material(material_id, title, source, authority, owner)
    client.app.state.database.materials.update_one(
        {"id": material_id},
        {"$set": record},
        upsert=True,
    )


def _private_material(material_id, title, source, authority, owner) -> dict:
    return {
        "id": material_id,
        "title": title,
        "summary": "",
        "source": source,
        "materialType": "文档",
        "authority": authority,
        "accessLevel": "private",
        "status": "active",
        "createdBy": owner,
    }


def test_author_mounts_material_and_submission_freezes_it(client: TestClient) -> None:
    auth = login(client)
    mounted = mount(client, auth, "m-kcsz")
    assert mounted["title"].startswith("高等学校课程思政")
    assert outbox_sequence(client, "material:m-kcsz") == 1
    assert client.get("/api/cases/c-draft-1/materials").json() == [mounted]
    assert transition(client, auth, "submit")["version"]["materials"] == [mounted]


def test_file_material_projection_is_downloadable_without_leaking_blob_id(
    client: TestClient,
) -> None:
    client.app.state.database.materials.insert_one(_file_material())
    auth = login(client)
    mounted = mount(client, auth, "m-file")
    frozen = transition(client, auth, "submit")["version"]["materials"][0]

    _assert_file_projection(client, mounted, frozen)


def _file_material() -> dict:
    return {
        "id": "m-file",
        "title": "课堂文件",
        "filename": "课堂文件.txt",
        "mediaType": "text/plain",
        "size": 12,
        "blobId": "private-storage-key",
        "accessLevel": "public",
        "status": "active",
        "createdBy": "u-admin-demo",
    }


def _assert_file_projection(client, mounted: dict, frozen: dict) -> None:
    assert mounted["filename"] == "课堂文件.txt"
    assert mounted["hasFile"] is True
    assert frozen == mounted
    assert "blobId" not in mounted and "blobId" not in frozen
    assert "blobId" not in client.get("/api/cases/c-draft-1/materials").text


def test_private_material_cannot_be_mounted_by_another_author(client: TestClient) -> None:
    auth = login(client)
    seed_private_material(client, "m-private-other", "他人私密素材", "校内", "original", "other")
    response = client.post(
        "/api/cases/c-draft-1/materials",
        headers=headers(auth),
        json={
            "materialId": "m-private-other",
            "revision": current_revision(client),
        },
    )
    assert response.status_code == 404


def test_unmount_records_material_catalog_change(client: TestClient) -> None:
    auth = login(client)
    mount(client, auth, "m-kcsz")
    mounted_sequence = outbox_sequence(client, "material:m-kcsz")

    unmount(client, auth, "m-kcsz")

    sequence = outbox_sequence(client, "material:m-kcsz")
    assert sequence > mounted_sequence
    assert revocation(client, "material:m-kcsz")["sequence"] == sequence


def test_author_can_list_an_owned_private_material(client: TestClient) -> None:
    auth = login(client)
    seed_private_material(
        client,
        "m-private-owned",
        "作者私密素材",
        "个人",
        "secondary",
        auth["user"]["id"],
    )
    mounted = mount(client, auth, "m-private-owned")
    assert mounted in client.get("/api/cases/c-draft-1/materials").json()


def test_snapshot_rollback_restores_material_relations(client: TestClient) -> None:
    auth = login(client)
    first = mount(client, auth, "m-kcsz")
    snapshot = transition(client, auth, "snapshot")["snapshot"]
    unmount(client, auth, first["id"])
    mount(client, auth, "m-kxjsh")
    before = outbox_sequence(client, "material:m-kxjsh")
    transition(client, auth, "rollback", targetId=snapshot["id"])
    rows = client.get("/api/cases/c-draft-1/materials").json()
    assert [row["id"] for row in rows] == [first["id"]]
    restored = outbox_sequence(client, "material:m-kcsz")
    assert restored == outbox_sequence(client, "material:m-kxjsh") > before
    assert revocation(client, "material:m-kxjsh")["sequence"] == restored


def publish_case_with_material(client: TestClient) -> tuple[dict, dict]:
    author = login(client)
    client.app.state.database.materials.update_one(
        {"id": "m-zrjs"},
        {"$set": {"filename": "校内材料.txt", "blobId": "private-campus-key"}},
    )
    mounted = mount(client, author, "m-zrjs")
    submitted = transition(client, author, "submit")
    admin = admin_login(client)
    started = transition_with_case(client, admin, "start", submitted["case"])
    approved = transition_with_case(
        client,
        admin,
        "approve",
        started["case"],
        submittedVersionId=submitted["version"]["id"],
    )
    client.post("/api/auth/logout", headers=headers(admin))
    return mounted, approved


def test_public_case_exposes_restricted_name_but_not_content(
    client: TestClient,
) -> None:
    mounted, approved = publish_case_with_material(client)
    anonymous = client.get("/api/cases/c-draft-1/materials")
    assert anonymous.status_code == 200
    row = next(row for row in anonymous.json() if row["id"] == mounted["id"])
    assert row == {
        "id": mounted["id"],
        "title": mounted["title"],
        "accessLevel": "campus",
        "contentAvailable": False,
        "hasFile": True,
    }
    assert "filename" not in row and "blobId" not in row
    assert approved["case"]["publicationStatus"] == "public"


def test_publication_transitions_maintain_material_reference_count(client: TestClient) -> None:
    mounted, approved = publish_case_with_material(client)
    database = client.app.state.database
    assert database.materials.find_one({"id": mounted["id"]})["publicReferenceCount"] == 1
    approved_sequence = assert_published_events(client, mounted["id"])
    admin = admin_login(client)
    hidden = transition_with_case(client, admin, "hide", approved["case"])
    assert database.materials.find_one({"id": mounted["id"]})["publicReferenceCount"] == 0
    hidden_sequence = assert_hidden_events(client, mounted["id"], approved_sequence)
    transition_with_case(client, admin, "restore", hidden["case"])
    assert database.materials.find_one({"id": mounted["id"]})["publicReferenceCount"] == 1
    restored_sequence = outbox_sequence(client, "case:c-draft-1")
    assert restored_sequence > hidden_sequence
    assert outbox_sequence(client, f"material:{mounted['id']}") == restored_sequence


def transition_with_case(
    client: TestClient, auth: dict, command: str, case: dict, **extra
) -> dict:
    body = {"command": command, "revision": case["revision"], **extra}
    response = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=headers(auth),
        json=body,
    )
    assert response.status_code == 200
    return response.json()


def create_submission(client: TestClient, auth: dict, title: str) -> dict:
    created = client.post(
        "/api/cases",
        headers=headers(auth),
        json={"title": title},
    ).json()
    mounted = client.post(
        f"/api/cases/{created['id']}/materials",
        headers=headers(auth),
        json={"materialId": "m-zrjs", "revision": created["revision"]},
    )
    assert mounted.status_code == 201
    case = client.get(f"/api/cases/{created['id']}").json()
    return transition_for(client, auth, created["id"], "submit", case)


def transition_for(client, auth, case_id, command, case, **extra) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/lifecycle",
        headers=headers(auth),
        json={"command": command, "revision": case["revision"], **extra},
    )
    assert response.status_code == 200
    return response.json()


def approve_submission(client, admin: dict, submission: dict) -> dict:
    case_id = submission["case"]["id"]
    started = transition_for(client, admin, case_id, "start", submission["case"])
    return transition_for(
        client,
        admin,
        case_id,
        "approve",
        started["case"],
        submittedVersionId=submission["version"]["id"],
    )


def admin_login(client: TestClient) -> dict:
    return client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    ).json()


def reference_count(client: TestClient) -> int:
    row = client.app.state.database.materials.find_one({"id": "m-zrjs"})
    return row["publicReferenceCount"]


def change_publication(client, case: dict, command: str) -> dict:
    return transition_for(
        client,
        admin_login(client),
        case["id"],
        command,
        case,
    )


def assert_reference_state(client, count: int) -> int:
    assert reference_count(client) == count
    return outbox_sequence(client, "material:m-zrjs")


def test_shared_material_remains_public_until_last_case_is_hidden(client: TestClient) -> None:
    author = login(client)
    first = create_submission(client, author, "公开引用一")
    second = create_submission(client, author, "公开引用二")
    admin = admin_login(client)
    first = approve_submission(client, admin, first)
    second = approve_submission(client, admin, second)
    approved_sequence = assert_reference_state(client, 2)
    first = change_publication(client, first["case"], "hide")
    first_hidden = assert_reference_state(client, 1)
    assert first_hidden > approved_sequence
    change_publication(client, second["case"], "hide")
    second_hidden = assert_reference_state(client, 0)
    assert second_hidden > first_hidden
    change_publication(client, first["case"], "restore")
    assert assert_reference_state(client, 1) > second_hidden
