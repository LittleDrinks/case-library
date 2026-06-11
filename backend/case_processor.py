#!/usr/bin/env python3
"""
强国有我大思政课案例库 - 案例处理模块
集成原有的Skill系统
"""

from pathlib import Path

# 导入数据库模块
from database import create_case, get_case, update_case

ROOT_DIR = Path(__file__).resolve().parent.parent
CLASSIFIER_PATH = ROOT_DIR / "skills" / "zhutifenlei" / "classifier.md"
TEMPLATE_DIR = ROOT_DIR / "skills" / "anlibianxie"


def classify_case(content: str) -> dict:
    """调用分类器判断案例类型"""
    try:
        if CLASSIFIER_PATH.exists():
            # 简单的关键词匹配分类（完整版本需要LLM）
            return _simple_classify(content)
        return {
            "primary_type": "TYPE_A",
            "types": ["TYPE_A"],
            "themes": ["校园文明"],
            "reason": "默认分类",
        }
    except Exception as e:
        print(f"分类失败: {e}")
        return {
            "primary_type": "TYPE_A",
            "types": ["TYPE_A"],
            "themes": ["校园文明"],
            "reason": "分类异常",
        }


def _simple_classify(content: str) -> dict:
    """简单关键词分类"""
    content_lower = content.lower()

    types = []
    themes = []

    # TYPE_A判断：党的创新理论、典型人物
    if any(
        keyword in content_lower
        for keyword in [
            "习近平",
            "新时代",
            "社会主义",
            "价值观",
            "典型人物",
            "先进事迹",
            "英雄",
            "榜样",
        ]
    ):
        types.append("TYPE_A")

    # TYPE_B判断：课程、教学、专业
    if any(
        keyword in content_lower
        for keyword in ["课程", "教学", "专业", "课堂", "实验室", "实习", "毕业设计"]
    ):
        types.append("TYPE_B")

    # TYPE_C判断：实践、志愿、服务
    if any(
        keyword in content_lower
        for keyword in ["实践", "志愿", "服务", "社区", "农村", "援疆", "帮扶", "劳动"]
    ):
        types.append("TYPE_C")

    # 如果都没匹配到，默认TYPE_A
    if not types:
        types.append("TYPE_A")

    # 主题分类
    if any(
        keyword in content_lower
        for keyword in [
            "国家战略",
            "科技",
            "芯片",
            "航天",
            "新能源",
            "人工智能",
            "援疆",
            "乡村振兴",
        ]
    ):
        themes.append("强国建设")

    if any(
        keyword in content_lower for keyword in ["上海", "五个中心", "长三角", "城市治理", "文化"]
    ):
        themes.append("上海实践")

    if any(
        keyword in content_lower
        for keyword in ["创新", "科技攻关", "专利", "成果转化", "3D打印", "AI"]
    ):
        themes.append("创新发展")

    if any(keyword in content_lower for keyword in ["文明", "志愿", "社区", "校园文化", "后勤"]):
        themes.append("校园文明")

    if not themes:
        themes.append("校园文明")

    return {"primary_type": types[0], "types": types, "themes": themes, "reason": "基于关键词匹配"}


def get_template(type_code: str) -> str | None:
    """获取模板"""
    template_map = {
        "TYPE_A": "template-sizhengke.md",
        "TYPE_B": "template-kechengsizheng.md",
        "TYPE_C": "template-shijian.md",
    }

    template_name = template_map.get(type_code)
    if template_name:
        template_path = TEMPLATE_DIR / template_name
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")

    return None


def generate_case_content(content: str, case_type: str, title: str = "") -> dict:
    """生成案例内容"""
    template = get_template(case_type)

    if not template:
        # 简单的默认模板
        default_templates = {
            "TYPE_A": {
                "title": title or "思政课教学案例",
                "content": content,
                "structure": {
                    "introduction": "引言部分",
                    "main_text": content,
                    "thinking_questions": ["思考题1", "思考题2"],
                    "references": [],
                },
            },
            "TYPE_B": {
                "title": title or "课程思政案例",
                "content": content,
                "structure": {
                    "course_name": "建议关联课程",
                    "teaching_goals": [],
                    "content": content,
                },
            },
            "TYPE_C": {
                "title": title or "实践育人案例",
                "content": content,
                "structure": {
                    "activity_name": "实践活动名称",
                    "participants": [],
                    "content": content,
                },
            },
        }
        return default_templates.get(case_type, default_templates["TYPE_A"])

    # 如果有模板，这里可以实现模板填充逻辑（简化版本）
    return {"title": title or "案例", "content": content, "structure": {}}


def extract_keywords(content: str, title: str = "") -> list[str]:
    """提取关键词"""
    keywords = []

    # 上海大学相关关键词
    if "上海大学" in content or "上大" in content:
        keywords.append("上海大学")

    if "文学院" in content:
        keywords.append("文学院")

    # 主题相关关键词
    theme_keywords = [
        "种子计划",
        "海鸥计划",
        "尚公计划",
        "社会脊梁",
        "习近平",
        "新时代",
        "社会主义核心价值观",
        "援疆",
        "乡村振兴",
        "志愿服务",
        "科技创新",
        "3D打印",
        "人工智能",
        "上海",
        "五个中心",
    ]

    for keyword in theme_keywords:
        if keyword in content:
            keywords.append(keyword)

    # 最多提取10个关键词
    return list(set(keywords))[:10]


def process_new_case(
    content: str,
    title: str = "",
    author: str = "",
    department: str = "",
    user_type: str = "",
    user_theme: str = "",
    owner_username: str = "",
) -> list[int]:
    """处理新案例，支持生成多个版本"""
    # 使用用户选择的类型和主题
    case_type = user_type.strip() if user_type and user_type.strip() else "TYPE_A"
    case_theme = user_theme.strip() if user_theme and user_theme.strip() else "校园文明"

    created_case_ids = []

    case_data = generate_case_content(content, case_type, title)
    keywords = extract_keywords(content, title)

    case_record = {
        "title": case_data.get("title", title or "案例"),
        "type": case_type,
        "theme": case_theme,
        "content": case_data.get("content", content),
        "author": author,
        "owner_username": owner_username,
        "department": department,
        "keywords": keywords,
        "status": "pending_review",
    }

    case_id = create_case(case_record)
    created_case_ids.append(case_id)

    return created_case_ids


def enhance_case(case_id: int, additional_info: str) -> bool:
    """增强案例内容"""
    case = get_case(case_id)

    if not case:
        return False

    current_content = case.get("content", "")
    enhanced_content = current_content + "\n\n【补充信息】\n" + additional_info

    return update_case(case_id, {"content": enhanced_content}, "system", "补充信息")


def get_case_type_name(type_code: str) -> str:
    """获取案例类型名称"""
    type_names = {
        "TYPE_A": "思政课教学案例",
        "TYPE_B": "课程思政共享资源案例",
        "TYPE_C": "实践育人案例",
    }
    return type_names.get(type_code, type_code)


if __name__ == "__main__":
    print("case processor module loaded")
