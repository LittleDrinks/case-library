from __future__ import annotations

from fastapi.testclient import TestClient

DRAFT_FIELDS = {"id", "title", "updatedAt"}


def login(client: TestClient, username: str = "user", password: str = "user123") -> dict:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()


def headers(auth: dict) -> dict:
    return {"X-CSRF-Token": auth["csrfToken"]}


def test_anonymous_draft_page_requires_login(client: TestClient) -> None:
    assert client.get("/api/cases/drafts").status_code == 401


def test_draft_page_lists_only_own_editable_drafts(client: TestClient) -> None:
    login(client)
    response = client.get("/api/cases/drafts")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == ["c-draft-1"]
    assert set(body["items"][0]) == DRAFT_FIELDS
    assert body["total"] == 1


def test_draft_page_searches_by_title_substring(client: TestClient) -> None:
    login(client)
    hit = client.get("/api/cases/drafts", params={"q": "供应链"}).json()
    miss = client.get("/api/cases/drafts", params={"q": "不存在的标题"}).json()

    assert [item["id"] for item in hit["items"]] == ["c-draft-1"]
    assert miss["items"] == []
    assert miss["total"] == 0


def test_draft_page_is_bounded_and_ordered_by_update_time(client: TestClient) -> None:
    auth = login(client)
    for index in range(205):
        created = client.post(
            "/api/cases", json={"title": f"批量草稿 {index:03d}"}, headers=headers(auth)
        )
        assert created.status_code == 200

    first = client.get("/api/cases/drafts").json()
    last = client.get("/api/cases/drafts", params={"page": 11}).json()

    assert first["total"] == 206
    assert len(first["items"]) == 20
    assert last["page"] == 11
    assert len(last["items"]) == 6
    updated = [item["updatedAt"] for item in first["items"]]
    assert all(left >= right for left, right in zip(updated, updated[1:]))


def test_draft_page_rejects_oversize_page_size(client: TestClient) -> None:
    login(client)
    response = client.get("/api/cases/drafts", params={"pageSize": 51})

    assert response.status_code == 422
