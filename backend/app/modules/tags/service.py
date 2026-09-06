"""标签目录领域服务：管理员维护标签组与标签，停用保留身份，检索侧校验标签身份。"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from pymongo import ASCENDING, ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.core.ids import new_id
from app.modules.cases.service import CaseError

GROUP_SORT = [("sortKey", ASCENDING), ("name", ASCENDING)]
GROUP_FIELDS = ("id", "name", "requiredForSubmission", "sortKey", "enabled")
TAG_FIELDS = ("id", "groupId", "name", "sortKey", "enabled")


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


def _raise_conflict(error: DuplicateKeyError) -> None:
    raise CaseError(409, "名称与现有标签目录冲突") from error


def _apply_update(collection, query: dict, changes: dict) -> dict:
    try:
        return collection.find_one_and_update(
            query,
            {"$set": {**changes, "updatedAt": _now()}},
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as error:
        _raise_conflict(error)


def list_groups(database: Database) -> list[dict]:
    groups = database.tag_groups.find().sort(GROUP_SORT)
    rows = defaultdict(list)
    for tag in database.tags.find().sort(GROUP_SORT):
        rows[tag["groupId"]].append(tag_view(tag))
    return [{**group_view(group), "tags": rows[group["id"]]} for group in groups]


def create_group(database: Database, body: dict, user: dict | None) -> dict:
    _require_admin(user)
    group = {
        "id": new_id("tgg"),
        **body,
        "enabled": True,
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    try:
        database.tag_groups.insert_one(group)
    except DuplicateKeyError as error:
        _raise_conflict(error)
    return group_view(group)


def update_group(database: Database, group_id: str, body: dict, user) -> dict:
    _require_admin(user)
    _group(database, group_id)
    changes = {key: value for key, value in body.items() if value is not None}
    return group_view(_apply_update(database.tag_groups, {"id": group_id}, changes))


def create_tag(database: Database, group_id: str, body: dict, user) -> dict:
    _require_admin(user)
    _group(database, group_id)
    tag = {
        "id": new_id("tag"),
        "groupId": group_id,
        **body,
        "enabled": True,
        "createdAt": _now(),
        "updatedAt": _now(),
    }
    try:
        database.tags.insert_one(tag)
    except DuplicateKeyError as error:
        _raise_conflict(error)
    return tag_view(tag)


def update_tag(database: Database, tag_id: str, body: dict, user) -> dict:
    _require_admin(user)
    _tag(database, tag_id)
    if body.get("groupId"):
        _group(database, body["groupId"])
    changes = {key: value for key, value in body.items() if value is not None}
    return tag_view(_apply_update(database.tags, {"id": tag_id}, changes))


def unknown_tag_ids(database: Database, tag_ids: list[str]) -> list[str]:
    """停用标签仍保留身份，历史引用不视为缺失。"""
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
    """返回启用必填组中未被覆盖的组；停用组不再约束投稿，缺组时阻止提交。"""
    required = list(
        database.tag_groups.find({"requiredForSubmission": True, "enabled": True})
    )
    if not required:
        return []
    chosen = set(tag_ids or [])
    group_ids = [group["id"] for group in required]
    rows = database.tags.find({"groupId": {"$in": group_ids}}, {"id": 1, "groupId": 1})
    covered = {row["groupId"] for row in rows if row["id"] in chosen}
    return [group_view(group) for group in required if group["id"] not in covered]
