from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

CARD_FIELDS = {
    "id",
    "title",
    "summary",
    "workflowStatus",
    "publicationStatus",
    "createdAt",
    "updatedAt",
    "publishedAt",
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "likes",
    "theoryPoints",
}


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200


def test_anonymous_public_list_returns_published_card_summaries(
    client: TestClient,
) -> None:
    response = client.get("/api/cases?scope=public")

    assert response.status_code == 200
    rows = response.json()
    assert {row["id"] for row in rows} == {"c-02", "c-05", "c-08", "c-11"}
    assert all(row["publicationStatus"] == "public" for row in rows)
    assert all(row["summary"] and set(row) == CARD_FIELDS for row in rows)


def test_my_list_requires_login_and_returns_only_owned_card_summaries(
    client: TestClient,
) -> None:
    assert client.get("/api/cases?scope=mine").status_code == 401
    login(client)

    response = client.get("/api/cases?scope=mine")

    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == ["c-pending-1", "c-draft-1"]
    assert all(row["ownerId"] == "u-user-demo" for row in rows)
    assert all(row["summary"] and set(row) == CARD_FIELDS | {"ownerId"} for row in rows)


def test_case_list_requires_an_explicit_scope(client: TestClient) -> None:
    assert client.get("/api/cases").status_code == 422


def test_admin_scope_lists_all_cases_for_admin_only(client: TestClient) -> None:
    login(client)
    assert client.get("/api/cases?scope=admin").status_code == 403
    client.cookies.clear()
    response = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert response.status_code == 200

    rows = client.get("/api/cases?scope=admin")

    assert rows.status_code == 200
    assert {row["id"] for row in rows.json()} == {
        "c-02",
        "c-05",
        "c-08",
        "c-11",
        "c-draft-1",
        "c-pending-1",
    }
    assert all("document" not in row and "ownerId" in row for row in rows.json())


def test_public_detail_ignores_admin_working_copy(client: TestClient) -> None:
    original = client.get("/api/cases/c-02/public").json()
    client.app.state.database.cases.update_one(
        {"id": "c-02"}, {"$set": {"title": "管理员工作副本标题"}}
    )
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})

    response = client.get("/api/cases/c-02/public")

    assert response.status_code == 200
    assert response.json()["title"] == original["title"]
    assert client.get("/api/cases/c-02").json()["title"] == "管理员工作副本标题"


def test_public_detail_does_not_expose_internal_metadata(client: TestClient) -> None:
    response = client.get("/api/cases/c-02/public")

    assert response.status_code == 200
    payload = response.json()
    assert "citations" not in payload
    assert "kit" not in payload
    assert "ownerId" not in payload
    assert "submittedVersionId" not in payload


@pytest.mark.parametrize("publication_status", ["none", "hidden", None])
def test_non_owner_cannot_distinguish_inaccessible_case_from_missing(
    client: TestClient, publication_status: str | None
) -> None:
    if publication_status:
        client.app.state.database.cases.update_one(
            {"id": "c-02"}, {"$set": {"publicationStatus": publication_status}}
        )
    login(client)

    response = client.get("/api/cases/c-02" if publication_status else "/api/cases/missing")

    assert response.status_code == 404
