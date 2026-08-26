from __future__ import annotations

from fastapi.testclient import TestClient


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def _import(client: TestClient, auth: dict, name: str, content: bytes) -> dict:
    response = client.post(
        "/api/admin/material-imports",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        data={"accessLevel": "public"},
        files=[("files", (name, content, "text/plain"))],
    )
    assert response.status_code == 201
    return response.json()["items"][0]


def _decide(client: TestClient, auth: dict, candidate_id: str, body: dict):
    return client.post(
        f"/api/admin/material-candidates/{candidate_id}/decision",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=body,
    )


def _candidate_record(index: int) -> dict:
    return {
        "id": f"page-{index:02d}",
        "filename": f"分页-{index:02d}.txt",
        "mediaType": "text/plain",
        "size": index,
        "accessLevel": "campus",
        "status": "candidate",
        "createdBy": "admin",
        "createdAt": f"2026-08-13T00:00:{index:02d}Z",
        "sha256": f"page-digest-{index:02d}",
        "blobId": f"page-blob-{index:02d}",
    }


def _seed_candidates(client: TestClient, count: int) -> None:
    collection = client.app.state.database.material_candidates
    for index in range(count):
        collection.insert_one(_candidate_record(index))


def _assert_candidate_page(payload: dict) -> None:
    assert (payload["total"], payload["page"], payload["pageSize"]) == (53, 2, 50)
    assert [row["id"] for row in payload["items"]] == [
        "page-02",
        "page-01",
        "page-00",
    ]


def _outbox_row(client: TestClient, logical_key: str) -> dict:
    return client.app.state.database.search_outbox.find_one({"_id": logical_key})


def _assert_approved_material(row: dict, item: dict, title: str) -> None:
    expected = _approved_material_expectation(item, title)
    actual = {field: row[field] for field in expected}
    assert actual == expected


def _approved_material_expectation(item: dict, title: str) -> dict:
    return {
        "id": item["candidateId"],
        "title": title,
        "filename": "待审文件.txt",
        "mediaType": "text/plain",
        "size": 14,
        "accessLevel": "public",
    }


def test_admin_approves_candidate_and_records_catalog_change(
    client: TestClient,
) -> None:
    auth = _login(client, "admin", "admin123")
    item = _import(client, auth, "待审文件.txt", b"review fixture")
    body = {"decision": "approve", "title": "批准后的教学素材"}

    response = _decide(client, auth, item["candidateId"], body)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["materialId"] == item["candidateId"]
    row = client.app.state.database.materials.find_one({"id": item["candidateId"]})
    _assert_approved_material(row, item, body["title"])
    event = _outbox_row(client, f"material:{item['candidateId']}")
    assert event["sequence"] > event["appliedSequence"]


def test_approval_preserves_imported_file_and_provenance(client: TestClient) -> None:
    auth = _login(client, "admin", "admin123")
    item = _import(client, auth, "原始文件.txt", b"durable fixture")
    candidate_id = item["candidateId"]

    _decide(client, auth, candidate_id, {"decision": "approve"})

    material = client.app.state.database.materials.find_one({"id": candidate_id})
    candidate = client.app.state.database.material_candidates.find_one(
        {"id": candidate_id}
    )
    assert material["blobId"] == candidate["blobId"]
    assert material["accessLevel"] == candidate["accessLevel"] == "public"
    assert material["provenance"]["candidateId"] == candidate_id
    assert material["title"] == "原始文件"


def test_admin_rejects_candidate_once(client: TestClient) -> None:
    auth = _login(client, "admin", "admin123")
    item = _import(client, auth, "拒绝文件.txt", b"reject fixture")
    candidate_id = item["candidateId"]

    rejected = _decide(client, auth, candidate_id, {"decision": "reject"})
    repeated = _decide(client, auth, candidate_id, {"decision": "approve"})

    assert rejected.json()["status"] == "rejected"
    assert repeated.status_code == 409
    key = f"material:{candidate_id}"
    assert client.app.state.database.search_outbox.find_one({"_id": key}) is None


def test_candidate_list_filters_pending_review(client: TestClient) -> None:
    auth = _login(client, "admin", "admin123")
    pending = _import(client, auth, "仍待审核.txt", b"pending fixture")
    decided = _import(client, auth, "已经审核.txt", b"decided fixture")
    _decide(client, auth, decided["candidateId"], {"decision": "reject"})

    response = client.get(
        "/api/admin/material-candidates", params={"status": "candidate"}
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [row["id"] for row in response.json()["items"]] == [pending["candidateId"]]


def test_candidate_list_is_bounded_and_paginated(client: TestClient) -> None:
    _login(client, "admin", "admin123")
    _seed_candidates(client, 53)

    response = client.get(
        "/api/admin/material-candidates",
        params={"page": 2, "pageSize": 50},
    )

    assert response.status_code == 200
    _assert_candidate_page(response.json())
    assert (
        client.get(
            "/api/admin/material-candidates",
            params={"pageSize": 51},
        ).status_code
        == 422
    )


def test_candidate_decision_requires_admin_and_csrf(client: TestClient) -> None:
    admin = _login(client, "admin", "admin123")
    item = _import(client, admin, "受保护.txt", b"protected fixture")
    candidate_id = item["candidateId"]
    missing_csrf = client.post(
        f"/api/admin/material-candidates/{candidate_id}/decision",
        json={"decision": "approve"},
    )
    user = _login(client, "user", "user123")
    forbidden = _decide(client, user, candidate_id, {"decision": "approve"})

    assert missing_csrf.status_code == 403
    assert forbidden.status_code == 403
