#!/usr/bin/env python3
"""Insert demo cases into MongoDB when the cases collection is empty."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import create_case, get_db, init_db, update_case

DEMO_CASES = [
    {
        "title": "新时代青年理想信念教育案例",
        "type": "TYPE_A",
        "theme": "强国建设",
        "content": "围绕新时代青年理想信念教育，设计课堂导入、案例研讨和延伸思考。",
        "author": "admin",
        "department": "马克思主义学院",
        "keywords": ["理想信念", "青年", "思政课"],
    },
    {
        "title": "工程伦理课程思政共享资源案例",
        "type": "TYPE_B",
        "theme": "数字赋能",
        "content": "结合工程伦理课程内容，引导学生理解技术责任、公共利益与家国情怀。",
        "author": "admin",
        "department": "教务处",
        "keywords": ["课程思政", "工程伦理", "共享资源"],
    },
    {
        "title": "社区志愿服务实践育人案例",
        "type": "TYPE_C",
        "theme": "实践育人",
        "content": "通过社区志愿服务项目，组织学生在真实场景中理解社会责任与基层治理。",
        "author": "admin",
        "department": "学生工作办公室",
        "keywords": ["实践育人", "志愿服务", "社区治理"],
    },
]


def init_demo_data():
    init_db()

    db = get_db()
    existing = db.cases.count_documents({})
    if existing > 0:
        print(f"Cases already exist: {existing}. Skip demo data initialization.")
        return

    for case in DEMO_CASES:
        case_id = create_case(case)
        update_case(
            case_id,
            {"status": "approved", "is_approved": True, "is_in_library": True},
            "system",
            "Approved demo case",
        )
        print(f"Created demo case: {case['title']} (ID: {case_id})")


if __name__ == "__main__":
    init_demo_data()
