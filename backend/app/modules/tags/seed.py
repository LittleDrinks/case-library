"""演示环境标签目录种子：默认组与标签均不设投稿必填。"""

from __future__ import annotations

from pymongo.database import Database

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("学科", ("马克思主义理论", "教育学", "历史学", "工学")),
    ("课程", ("习近平新时代中国特色社会主义思想概论", "中国近现代史纲要", "自然辩证法概论")),
    ("案例类型", ("人物传记类", "校本实践类", "课堂教学类", "社会实践类")),
    ("思政元素", ("科学家精神", "爱国主义教育", "文化自信", "劳动教育", "大思政课建设")),
)


def seed_demo_tags(database: Database) -> None:
    for sort_key, (group_name, tags) in enumerate(GROUPS):
        group = database.tag_groups.find_one({"name": group_name})
        if not group:
            group = {
                "id": f"tgg-seed-{sort_key + 1}",
                "name": group_name,
                "requiredForSubmission": False,
                "sortKey": sort_key,
            }
            database.tag_groups.insert_one(group)
        for tag_sort, tag_name in enumerate(tags):
            _seed_tag(database, group["id"], tag_name, tag_sort)


def _seed_tag(database: Database, group_id: str, tag_name: str, sort_key: int) -> None:
    if database.tags.find_one({"groupId": group_id, "name": tag_name}):
        return
    database.tags.insert_one(
        {
            "id": f"tag-seed-{group_id.removeprefix('tgg-seed-')}-{sort_key + 1}",
            "groupId": group_id,
            "name": tag_name,
            "sortKey": sort_key,
        }
    )
