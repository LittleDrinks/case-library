"""标签目录领域服务：管理员维护标签组与标签，检索侧校验标签身份。"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from pymongo import ASCENDING, ReturnDocument
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.cases.service import CaseError

GROUP_SORT = [("sortKey", ASCENDING), ("name", ASCENDING)]
GROUP_FIELDS = ("id", "name", "requiredForSubmission", "sortKey")
TAG_FIELDS = ("id", "groupId", "name", "sortKey")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_admin(user: dict | None) -> None:
    if not user or user["role"] != "admin":
        raise CaseError(403, "仅管理员可维护标签目录")


def group_view(group: dict) -> dict:
    return {key: group.get(key) for key in GROUP_FIELDS}


def tag_view(tag: dict) -> dict:
    return {key: tag.get(key) for key in TAG_FIELDS}


def _group(database: Database, group_id: str) -> dict:
    group = database.tag_groups.find_one({"id": group_id})
    if not group:
        raise CaseError(404, "标签组不存在")
    return group


def _tag(database: Database, tag_id: str) -> dict:
    tag = database.tags.find_one({"id": tag_id})
    if not tag:
        raise CaseError(404, "标签不存在")
    return tag


def _assert_group_name_free(database: Database, name: str, exclude: str = "") -> None:
    query = {"name": name, "id": {"$ne": exclude}}
    if database.tag_groups.find_one(query):
        raise CaseError(409, "同名标签组已存在")


def _assert_tag_name_free(
    database: Database, group_id: str, name: str, exclude: str = ""
) -> None:
    query = {"groupId": group_id, "name": name, "id": {"$ne": exclude}}
    if database.tags.find_one(query):
        raise CaseError(409, "该标签组内已存在同名标签")


def list_groups(database: Database) -> list[dict]:
    groups = database.tag_groups.find().sort(GROUP_SORT)
    rows = defaultdict(list)
    for tag in database.tags.find().sort(GROUP_SORT):
        rows[tag["groupId"]].append(tag_view(tag))
    return [{**group_view(group), "tags": rows[group["id"]]} for group in groups]


def create_group(database: Database, body: dict, user: dict | None) -> dict:
    _require_admin(user)
    _assert_group_name_free(database, body["name"])
    group = {"id": new_id("tgg"), **body, "createdAt": _now(), "updatedAt": _now()}
    database.tag_groups.insert_one(group)
    return group_view(group)


def update_group(database: Database, group_id: str, body: dict, user) -> dict:
    _require_admin(user)
    _group(database, group_id)
    if body.get("name"):
        _assert_group_name_free(database, body["name"], exclude=group_id)
    changes = {key: value for key, value in body.items() if value is not None}
    updated = database.tag_groups.find_one_and_update(
        {"id": group_id},
        {"$set": {**changes, "updatedAt": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    return group_view(updated)


def delete_group(database: Database, group_id: str, user) -> dict:
    _require_admin(user)
    _group(database, group_id)
    if database.tags.find_one({"groupId": group_id}):
        raise CaseError(409, "标签组内仍有标签，不能删除")
    database.tag_groups.delete_one({"id": group_id})
    return {"status": "deleted"}


def create_tag(database: Database, group_id: str, body: dict, user) -> dict:
    _require_admin(user)
    _group(database, group_id)
    _assert_tag_name_free(database, group_id, body["name"])
    tag = {
        "id": new_id("tag"),
        "groupId": group_id,
        **body,
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    database.tags.insert_one(tag)
    return tag_view(tag)


def update_tag(database: Database, tag_id: str, body: dict, user) -> dict:
    _require_admin(user)
    current = _tag(database, tag_id)
    target_group = body.get("groupId") or current["groupId"]
    if body.get("groupId"):
        _group(database, target_group)
    name = body.get("name") or current["name"]
    _assert_tag_name_free(database, target_group, name, exclude=tag_id)
    changes = {key: value for key, value in body.items() if value is not None}
    updated = database.tags.find_one_and_update(
        {"id": tag_id},
        {"$set": {**changes, "updatedAt": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    return tag_view(updated)


def _tag_in_use(database: Database, tag_id: str) -> bool:
    if database.cases.find_one({"tagIds": tag_id}):
        return True
    return bool(database.case_versions.find_one({"metadata.tagIds": tag_id}))


def delete_tag(database: Database, tag_id: str, user) -> dict:
    _require_admin(user)
    _tag(database, tag_id)
    if _tag_in_use(database, tag_id):
        raise CaseError(409, "标签已被案例使用，不能删除")
    database.tags.delete_one({"id": tag_id})
    return {"status": "deleted"}


def unknown_tag_ids(database: Database, tag_ids: list[str]) -> list[str]:
    wanted = list(dict.fromkeys(tag_ids))
    found = set(database.tags.distinct("id", {"id": {"$in": wanted}}))
    return sorted(set(wanted) - found)


def ensure_tags_exist(database: Database, tag_ids: list[str]) -> None:
    if not tag_ids:
        return
    missing = unknown_tag_ids(database, tag_ids)
    if missing:
        raise CaseError(422, f"标签不存在或已删除: {', '.join(missing)}")


def validate_submission_tags(database: Database, tag_ids: list[str]) -> list[dict]:
    """返回给定标签集合未覆盖的必填组；投稿流程据此阻止缺组提交。"""
    required = list(database.tag_groups.find({"requiredForSubmission": True}))
    if not required:
        return []
    chosen = set(tag_ids or [])
    group_ids = [group["id"] for group in required]
    rows = database.tags.find({"groupId": {"$in": group_ids}}, {"id": 1, "groupId": 1})
    covered = {row["groupId"] for row in rows if row["id"] in chosen}
    return [group_view(group) for group in required if group["id"] not in covered]
