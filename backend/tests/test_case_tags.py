"""案例 tagIds 保存、回显与投稿必填组校验（Issue 163）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

TAG_SEEDED = "tag-seed-4-1"


def _auth(client: TestClient, username: str = "user") -> dict:
    session = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"{username}123"},
    ).json()
    assert session.get("csrfToken"), session
    return {"X-CSRF-Token": session["csrfToken"]}


def _create_case(client: TestClient, auth: dict) -> dict:
    document = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "正文"}]}],
    }
    return client.post(
        "/api/cases", headers=auth, json={"title": "标签案例", "document": document}
    ).json()


def _save_tags(client: TestClient, auth: dict, case: dict, tag_ids: list) -> dict:
    return client.patch(
        f"/api/cases/{case['id']}",
        headers=auth,
        json={"tagIds": tag_ids, "revision": case["revision"]},
    )


def test_case_saves_and_restores_tag_ids(client: TestClient) -> None:
    auth = _auth(client)
    case = _create_case(client, auth)
    saved = _save_tags(client, auth, case, [TAG_SEEDED, TAG_SEEDED, "tag-seed-4-2"])
    assert saved.status_code == 200
    assert saved.json()["tagIds"] == [TAG_SEEDED, "tag-seed-4-2"]
    restored = client.get(f"/api/cases/{case['id']}", headers=auth).json()
    assert restored["tagIds"] == [TAG_SEEDED, "tag-seed-4-2"]


def test_case_rejects_unknown_tag_ids(client: TestClient) -> None:
    auth = _auth(client)
    case = _create_case(client, auth)
    saved = _save_tags(client, auth, case, ["tag-missing"])
    assert saved.status_code == 422


def test_submit_blocks_missing_required_group(client: TestClient) -> None:
    owner = _auth(client)
    case = _create_case(client, owner)
    admin = _auth(client, "admin")
    group = client.post(
        "/api/tag-groups",
        headers=admin,
        json={"name": "投稿必填组", "requiredForSubmission": True},
    ).json()
    tag = client.post(
        f"/api/tag-groups/{group['id']}/tags", headers=admin, json={"name": "必填标签"}
    ).json()
    owner = _auth(client)
    blocked = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers=owner,
        json={"command": "submit", "revision": case["revision"]},
    )
    assert blocked.status_code == 422
    assert "投稿必填组" in blocked.json()["detail"]
    _save_tags(client, owner, case, [tag["id"]])
    allowed = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers=owner,
        json={"command": "submit", "revision": case["revision"] + 1},
    )
    assert allowed.status_code == 200
    versions = allowed.json()["version"]
    assert versions["metadata"]["tagIds"] == [tag["id"]]
