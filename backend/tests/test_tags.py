"""标签目录 API、提交校验服务与案例 tagIds 保存的契约测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.modules.cases.service import CaseError
from app.modules.tags.service import ensure_tags_exist, validate_submission_tags

TGG_SEEDED = "tgg-seed-4"
TAG_SEEDED = "tag-seed-4-1"


def login(client: TestClient, username: str = "admin") -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"{username}123"},
    )
    return response.json()


def _csrf(client: TestClient, username: str = "admin") -> dict:
    return {"X-CSRF-Token": login(client, username)["csrfToken"]}


def test_catalog_lists_seeded_groups_publicly(client: TestClient) -> None:
    groups = client.get("/api/tag-groups").json()
    names = {group["name"]: group for group in groups}
    assert set(names) == {"学科", "课程", "案例类型", "思政元素"}
    assert all(group["requiredForSubmission"] is False for group in groups)
    elements = names["思政元素"]["tags"]
    assert {"id": TAG_SEEDED, "name": "科学家精神"}.items() <= set(
        elements[0].items()
    )


def test_admin_manages_groups_and_tags(client: TestClient) -> None:
    auth = _csrf(client)
    group = _create_group(client, auth, "育人场域", True)
    assert group == {
        "id": group["id"],
        "name": "育人场域",
        "requiredForSubmission": True,
        "sortKey": 0,
    }
    renamed = client.patch(
        f"/api/tag-groups/{group['id']}", headers=auth, json={"name": "育人场景"}
    )
    assert renamed.json()["name"] == "育人场景"
    _assert_group_and_tag_lifecycle(client, auth, group["id"])


def _assert_group_and_tag_lifecycle(client: TestClient, auth: dict, group_id: str) -> None:
    tag = client.post(
        f"/api/tag-groups/{group_id}/tags", headers=auth, json={"name": "场馆育人"}
    )
    assert tag.status_code == 201
    assert client.delete(f"/api/tag-groups/{group_id}", headers=auth).status_code == 409
    assert client.delete(f"/api/tags/{tag.json()['id']}", headers=auth).status_code == 200
    assert client.delete(f"/api/tag-groups/{group_id}", headers=auth).status_code == 200


def _create_group(client: TestClient, auth: dict, name: str, required: bool) -> dict:
    created = client.post(
        "/api/tag-groups",
        headers=auth,
        json={"name": name, "requiredForSubmission": required},
    )
    assert created.status_code == 201
    return created.json()


def test_catalog_writes_require_admin_and_csrf(client: TestClient) -> None:
    assert (
        client.post("/api/tag-groups", json={"name": "匿名组"}).status_code == 401
    )
    user = _csrf(client, "user")
    assert (
        client.post("/api/tag-groups", headers=user, json={"name": "教师组"}).status_code
        == 403
    )
    no_csrf = {"X-CSRF-Token": "wrong"}
    assert (
        client.post(
            "/api/tag-groups", headers=no_csrf, json={"name": "校验组"}
        ).status_code
        == 403
    )


def test_group_and_tag_names_stay_unique(client: TestClient) -> None:
    auth = _csrf(client)
    duplicate_group = client.post(
        "/api/tag-groups", headers=auth, json={"name": "学科"}
    )
    assert duplicate_group.status_code == 409
    group = client.post(
        "/api/tag-groups", headers=auth, json={"name": "重复检查组"}
    ).json()
    assert _create_tag(client, auth, group["id"], "同名词") == 201
    assert _create_tag(client, auth, group["id"], "同名词") == 409


def _create_tag(client: TestClient, auth: dict, group_id: str, name: str) -> int:
    return client.post(
        f"/api/tag-groups/{group_id}/tags", headers=auth, json={"name": name}
    ).status_code


def test_tag_delete_rejected_while_referenced(client: TestClient) -> None:
    database = client.app.state.database
    database.cases.insert_one({"id": "c-tagged", "tagIds": [TAG_SEEDED]})
    response = client.delete(f"/api/tags/{TAG_SEEDED}", headers=_csrf(client))
    assert response.status_code == 409
    database.cases.delete_one({"id": "c-tagged"})


def test_unknown_group_and_tag_are_not_found(client: TestClient) -> None:
    auth = _csrf(client)
    assert client.patch("/api/tag-groups/tgg-none", headers=auth, json={"name": "x"}).status_code == 404
    assert client.post("/api/tag-groups/tgg-none/tags", headers=auth, json={"name": "x"}).status_code == 404
    assert client.patch("/api/tags/tag-none", headers=auth, json={"sortKey": 3}).status_code == 404


def test_validate_submission_tags_reports_uncovered_required_groups(
    client: TestClient,
) -> None:
    database = client.app.state.database
    assert validate_submission_tags(database, []) == []
    group = client.post(
        "/api/tag-groups", headers=_csrf(client), json={"name": "必填组", "requiredForSubmission": True}
    ).json()
    tag = client.post(
        f"/api/tag-groups/{group['id']}/tags", headers=_csrf(client), json={"name": "必填标签"}
    ).json()
    missing = validate_submission_tags(database, [])
    assert missing == [{"id": group["id"], "name": "必填组", "requiredForSubmission": True, "sortKey": 0}]
    assert validate_submission_tags(database, [tag["id"]]) == []
    assert validate_submission_tags(database, [TAG_SEEDED]) == missing


def test_ensure_tags_exist_rejects_unknown_ids(client: TestClient) -> None:
    database = client.app.state.database
    ensure_tags_exist(database, [])
    ensure_tags_exist(database, [TAG_SEEDED])
    with pytest.raises(CaseError) as error:
        ensure_tags_exist(database, ["tag-missing"])
    assert error.value.status_code == 422
    assert "tag-missing" in error.value.detail


def test_case_patch_saves_owner_tag_ids_and_snapshots_metadata(
    client: TestClient,
) -> None:
    auth = _csrf(client, "user")
    case = client.get("/api/cases/c-draft-1").json()
    saved = client.patch(
        "/api/cases/c-draft-1",
        headers=auth,
        json={"revision": case["revision"], "tagIds": [TAG_SEEDED, TAG_SEEDED, "tag-seed-1-4"]},
    )
    assert saved.status_code == 200
    assert saved.json()["tagIds"] == [TAG_SEEDED, "tag-seed-1-4"]

    bad = client.patch(
        "/api/cases/c-draft-1",
        headers=auth,
        json={"revision": saved.json()["revision"], "tagIds": ["tag-missing"]},
    )
    assert bad.status_code == 422


def test_submitted_version_snapshot_carries_tag_ids(client: TestClient) -> None:
    owner = _csrf(client, "user")
    case = client.get("/api/cases/c-draft-1").json()
    tagged = client.patch(
        "/api/cases/c-draft-1",
        headers=owner,
        json={"revision": case["revision"], "tagIds": [TAG_SEEDED]},
    ).json()
    submitted = client.post(
        "/api/cases/c-draft-1/lifecycle",
        headers=owner,
        json={"command": "submit", "revision": tagged["revision"]},
    )
    assert submitted.status_code == 200
    metadata = submitted.json()["version"]["metadata"]
    assert metadata["tagIds"] == [TAG_SEEDED]
