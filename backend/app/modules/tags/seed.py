"""演示环境标签目录种子：稳定 ID upsert，重启不覆盖管理员改名与停用。"""

from __future__ import annotations

from pymongo.database import Database

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("学科", ("马克思主义理论", "教育学", "历史学", "工学")),
    ("课程", ("习近平新时代中国特色社会主义思想概论", "中国近现代史纲要", "自然辩证法概论")),
    ("案例类型", ("人物传记类", "校本实践类", "课堂教学类", "社会实践类")),
    ("思政元素", ("科学家精神", "爱国主义教育", "文化自信", "劳动教育", "大思政课建设")),
)


def seed_demo_tags(database: Database) -> None:
    for group_sort, (group_name, tags) in enumerate(GROUPS):
        group_number = group_sort + 1
        database.tag_groups.update_one(
            {"id": _group_id(group_number)},
            {"$setOnInsert": _group_document(group_name, group_number)},
            upsert=True,
        )
        for tag_sort, tag_name in enumerate(tags):
            database.tags.update_one(
                {"id": _tag_id(group_number, tag_sort + 1)},
                {"$setOnInsert": _tag_document(group_number, tag_sort + 1, tag_name)},
                upsert=True,
            )


def _group_id(group_number: int) -> str:
    return f"tgg-seed-{group_number}"


def _tag_id(group_number: int, tag_number: int) -> str:
    return f"tag-seed-{group_number}-{tag_number}"


def _group_document(name: str, group_number: int) -> dict:
    return {
        "id": _group_id(group_number),
        "name": name,
        "requiredForSubmission": False,
        "sortKey": group_number - 1,
        "enabled": True,
    }


def _tag_document(group_number: int, tag_number: int, name: str) -> dict:
    return {
        "id": _tag_id(group_number, tag_number),
        "groupId": _group_id(group_number),
        "name": name,
        "sortKey": tag_number - 1,
        "enabled": True,
    }
