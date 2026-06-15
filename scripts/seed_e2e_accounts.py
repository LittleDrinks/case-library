#!/usr/bin/env python3
"""Create deterministic alpha accounts and demo cases for browser/E2E tests."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from database import (
    create_case,
    create_user,
    get_db,
    get_user_by_username,
    init_db,
    review_case,
    set_user_password,
    submit_for_review,
    update_user_fields,
)


ACCOUNTS = [
    {
        "username": "e2e_user",
        "password": "E2eUserPass123!",
        "role": "normal",
        "nickname": "E2E作者",
        "must_change_password": False,
        "status": "active",
    },
    {
        "username": "e2e_admin",
        "password": "E2eAdminPass123!",
        "role": "admin",
        "nickname": "E2E管理员",
        "must_change_password": False,
        "status": "active",
    },
    {
        "username": "10000002",
        "password": "default123456",
        "role": "admin",
        "nickname": "小李",
        # Local demo/E2E admin for reviewer walkthroughs. Production/default
        # init users still require password change in backend/init_users.py.
        "must_change_password": False,
        "status": "active",
    },
]

DEMO_CASES = [
    {
        "title": "Alpha公开案例：社区治理实践育人",
        "type": "TYPE_C",
        "theme": "实践育人",
        "content": (
            "上海大学学生团队围绕社区治理开展实践调研。\n"
            "教师将基层治理议题转化为课堂讨论任务，引导学生理解人民城市理念。"
        ),
        "source_material": "来源材料：上海大学社区实践活动新闻摘录，含活动时间、地点、参与学院和社区反馈。",
        "status": "approved",
        "review_comment": "演示数据：通过入库。",
    },
    {
        "title": "Alpha待审核案例：工程伦理课程思政",
        "type": "TYPE_B",
        "theme": "数字赋能",
        "content": (
            "本案例围绕工程伦理课程中的算法责任展开。\n"
            "课堂通过真实技术场景讨论公共利益、职业伦理与家国责任。"
        ),
        "source_material": "来源材料：课程教学大纲、课堂讨论记录和学生反馈摘要。",
        "status": "pending_review",
    },
    {
        "title": "Alpha退回修改案例：理想信念课堂导入",
        "type": "TYPE_A",
        "theme": "强国建设",
        "content": (
            "教师以校史人物故事导入理想信念主题。\n"
            "当前稿件对来源和课堂互动设计描述不足。"
        ),
        "source_material": "来源材料：校史馆公开资料摘录，缺少课堂反馈记录。",
        "status": "needs_revision",
        "review_comment": "演示数据：请补充课堂互动和来源支撑。",
    },
    {
        "title": "Alpha草稿案例：数字赋能思政资源整理",
        "type": "TYPE_B",
        "theme": "数字赋能",
        "content": "教师正在整理数字资源支撑课程思政的案例正文。",
        "source_material": "来源材料：待补充平台资源链接和课堂使用记录。",
        "status": "draft",
    },
]


def upsert_account(account: dict) -> None:
    existing = get_user_by_username(account["username"])
    if existing:
        update_user_fields(
            account["username"],
            role=account["role"],
            nickname=account["nickname"],
            status=account["status"],
        )
        set_user_password(
            account["username"],
            account["password"],
            must_change_password=account["must_change_password"],
        )
        print(f"Updated account: {account['username']}")
        return

    create_user(**account)
    print(f"Created account: {account['username']}")


def reset_demo_cases() -> None:
    db = get_db()
    titles = [case["title"] for case in DEMO_CASES]
    existing_ids = [row["id"] for row in db.cases.find({"title": {"$in": titles}}, {"id": 1})]
    if existing_ids:
        db.cases.delete_many({"id": {"$in": existing_ids}})
        db.versions.delete_many({"case_id": {"$in": existing_ids}})
        db.reviews.delete_many({"case_id": {"$in": existing_ids}})

    for item in DEMO_CASES:
        case_id = create_case(
            {
                "title": item["title"],
                "type": item["type"],
                "theme": item["theme"],
                "content": item["content"],
                "source_material": item["source_material"],
                "author": "E2E作者",
                "owner_username": "e2e_user",
                "department": "马克思主义学院",
                "status": "draft",
                "keywords": ["alpha", item["theme"], item["type"]],
            }
        )
        if item["status"] in {"pending_review", "approved", "needs_revision"}:
            submit_for_review(case_id)
        if item["status"] == "approved":
            review_case(case_id, "e2e_admin", item["review_comment"], "approved")
        elif item["status"] == "needs_revision":
            review_case(case_id, "e2e_admin", item["review_comment"], "rejected")
        print(f"Seeded alpha case: {item['title']} ({item['status']})")


def main() -> None:
    if os.environ.get("ENABLE_DEMO_SEED", "").lower() not in {"1", "true", "yes"}:
        print("ENABLE_DEMO_SEED is not enabled; skipping e2e/demo seed.")
        return

    init_db()
    for account in ACCOUNTS:
        upsert_account(account)
    reset_demo_cases()


if __name__ == "__main__":
    main()
