"""标签目录 API 与提交校验服务的契约测试（停用保留身份；案例 tagIds 保存归后续票）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.modules.cases.service import CaseError
from app.modules.tags.seed import seed_demo_tags
from app.modules.tags.service import (
    ensure_tags_exist,
    unknown_tag_ids,
    validate_submission_tags,
)

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
    assert all(group["enabled"] is True for group in groups)
    assert all(tag["enabled"] is True for group in groups for tag in group["tags"])
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
        "enabled": True,
    }
    renamed = client.patch(
        f"/api/tag-groups/{group['id']}", headers=auth, json={"name": "育人场景"}
    )
    assert renamed.json()["name"] == "育人场景"
    _assert_group_and_tag_disable_lifecycle(client, auth, group["id"])


def _assert_group_and_tag_disable_lifecycle(
    client: TestClient, auth: dict, group_id: str
) -> None:
    tag = client.post(
        f"/api/tag-groups/{group_id}/tags", headers=auth, json={"name": "场馆育人"}
    )
    assert tag.status_code == 201
    disabled_tag = client.patch(
        f"/api/tags/{tag.json()['id']}", headers=auth, json={"enabled": False}
    )
    assert disabled_tag.json()["enabled"] is False
    disabled_group = client.patch(
        f"/api/tag-groups/{group_id}", headers=auth, json={"enabled": False}
    )
    assert disabled_group.json()["enabled"] is False
    catalog = client.get("/api/tag-groups").json()
    saved = {row["id"]: row for row in catalog}[group_id]
    assert saved["enabled"] is False
    assert saved["tags"][0]["enabled"] is False


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
    assert client.get("/api/tag-groups").status_code == 200


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


def test_tag_move_updates_the_real_group(client: TestClient) -> None:
    auth = _csrf(client)
    source = _create_group(client, auth, "迁出组", False)
    target = _create_group(client, auth, "迁入组", False)
    tag = client.post(
        f"/api/tag-groups/{source['id']}/tags", headers=auth, json={"name": "迁移标签"}
    ).json()

    moved = client.patch(
        f"/api/tags/{tag['id']}", headers=auth, json={"groupId": target["id"]}
    )

    assert moved.status_code == 200
    assert moved.json()["groupId"] == target["id"]
    groups = {row["id"]: row for row in client.get("/api/tag-groups").json()}
    assert groups[source["id"]]["tags"] == []
    assert [row["name"] for row in groups[target["id"]]["tags"]] == ["迁移标签"]


def test_tag_save_with_unchanged_name_succeeds(client: TestClient) -> None:
    auth = _csrf(client)
    group = _create_group(client, auth, "保留组", False)
    tag = client.post(
        f"/api/tag-groups/{group['id']}/tags", headers=auth, json={"name": "专名"}
    ).json()

    saved = client.patch(
        f"/api/tags/{tag['id']}", headers=auth, json={"name": "专名", "sortKey": 2}
    )

    assert saved.status_code == 200
    assert saved.json()["name"] == "专名"
    assert saved.json()["sortKey"] == 2


def test_tag_move_onto_existing_name_is_an_explicit_conflict(client: TestClient) -> None:
    auth = _csrf(client)
    source = _create_group(client, auth, "冲突源组", False)
    target = _create_group(client, auth, "冲突目标组", False)
    assert (
        client.post(
            f"/api/tag-groups/{target['id']}/tags", headers=auth, json={"name": "撞名"}
        ).status_code
        == 201
    )
    tag = client.post(
        f"/api/tag-groups/{source['id']}/tags", headers=auth, json={"name": "撞名"}
    ).json()

    moved = client.patch(
        f"/api/tags/{tag['id']}", headers=auth, json={"groupId": target["id"]}
    )

    assert moved.status_code == 409


def _create_tag(client: TestClient, auth: dict, group_id: str, name: str) -> int:
    return client.post(
        f"/api/tag-groups/{group_id}/tags", headers=auth, json={"name": name}
    ).status_code


def test_physical_deletion_is_not_available(client: TestClient) -> None:
    auth = _csrf(client)
    assert client.delete(f"/api/tag-groups/{TGG_SEEDED}", headers=auth).status_code == 405
    assert client.delete(f"/api/tags/{TAG_SEEDED}", headers=auth).status_code == 405


def test_unknown_group_and_tag_are_not_found(client: TestClient) -> None:
    auth = _csrf(client)
    assert client.patch("/api/tag-groups/tgg-none", headers=auth, json={"name": "x"}).status_code == 404
    assert client.post("/api/tag-groups/tgg-none/tags", headers=auth, json={"name": "x"}).status_code == 404
    assert client.patch("/api/tags/tag-none", headers=auth, json={"sortKey": 3}).status_code == 404


def test_validate_submission_tags_reports_uncovered_required_groups(
    client: TestClient,
) -> None:
    database = client.app.state.database
    auth = _csrf(client)
    assert validate_submission_tags(database, []) == []
    group = _create_group(client, auth, "必填组", True)
    tag = client.post(f"/api/tag-groups/{group['id']}/tags", headers=auth, json={"name": "必填标签"}).json()
    missing = validate_submission_tags(database, [])
    assert missing == [{
        "id": group["id"],
        "name": "必填组",
        "requiredForSubmission": True,
        "sortKey": 0,
        "enabled": True,
    }]
    assert validate_submission_tags(database, [tag["id"]]) == []
    assert validate_submission_tags(database, [TAG_SEEDED]) == missing


def test_disabled_required_group_no_longer_blocks_submission(
    client: TestClient,
) -> None:
    database = client.app.state.database
    auth = _csrf(client)
    group = client.post(
        "/api/tag-groups", headers=auth, json={"name": "停用必填组", "requiredForSubmission": True}
    ).json()
    assert validate_submission_tags(database, []) != []
    client.patch(f"/api/tag-groups/{group['id']}", headers=auth, json={"enabled": False})
    assert validate_submission_tags(database, []) == []


def test_disabled_tag_keeps_identity_for_history(client: TestClient) -> None:
    database = client.app.state.database
    client.patch(
        f"/api/tags/{TAG_SEEDED}", headers=_csrf(client), json={"enabled": False}
    )
    ensure_tags_exist(database, [TAG_SEEDED])
    assert unknown_tag_ids(database, [TAG_SEEDED]) == []


def test_ensure_tags_exist_rejects_unknown_ids(client: TestClient) -> None:
    database = client.app.state.database
    ensure_tags_exist(database, [])
    ensure_tags_exist(database, [TAG_SEEDED])
    with pytest.raises(CaseError) as error:
        ensure_tags_exist(database, ["tag-missing"])
    assert error.value.status_code == 422
    assert "tag-missing" in error.value.detail


def test_seed_rerun_preserves_admin_changes(client: TestClient) -> None:
    database = client.app.state.database
    auth = _csrf(client)
    client.patch(
        f"/api/tags/{TAG_SEEDED}",
        headers=auth,
        json={"name": "管理员改名", "enabled": False},
    )
    client.patch(
        f"/api/tag-groups/{TGG_SEEDED}", headers=auth, json={"name": "管理员改组名"}
    )

    seed_demo_tags(database)

    tag = database.tags.find_one({"id": TAG_SEEDED})
    assert tag["name"] == "管理员改名"
    assert tag["enabled"] is False
    group = database.tag_groups.find_one({"id": TGG_SEEDED})
    assert group["name"] == "管理员改组名"
