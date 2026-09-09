from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent

from app.modules.tags.service import list_groups


agent = Agent(
    output_type=str,
    name="case-library-agent",
    defer_model_check=True,
)
_PROMPT_DIR = Path(__file__).parent / "prompts"

_COURSE_CONTEXT_FIELDS = (
    ("course", "课程"),
    ("typeName", "案例类型"),
    ("stageText", "适用阶段"),
    ("audience", "适用对象"),
    ("purpose", "教学用途"),
    ("theoryPoints", "理论/思政要点"),
)

# 与 frontend/src/lib/searchFilters.js 的既有显示映射保持一致；这里只做上下文展示。
_AUDIENCE_LABELS = {"grad": "研究生", "ug": "本科", "embed": "专业课融入"}


def prompt_text(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def _current_date() -> str:
    """Return the current calendar date in Beijing time for the model context."""
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _context_value(value: object) -> str:
    if value is None or value == "" or value == []:
        return "未提供（不得推断）"
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value) or "未提供（不得推断）"
    return str(value)


def _tag_groups(database, case: dict) -> dict[str, list[str]]:
    tag_ids = set(case.get("tagIds") or [])
    if not tag_ids or database is None:
        return {}
    return {
        group["name"]: [
            tag["name"] for tag in group.get("tags", []) if tag.get("id") in tag_ids
        ]
        for group in list_groups(database)
        if any(tag.get("id") in tag_ids for tag in group.get("tags", []))
    }


def _audience_label(value: object) -> object:
    return _AUDIENCE_LABELS.get(value, value) if isinstance(value, str) else value


def _context_fields(case: dict, tag_groups: dict, has_tag_ids: bool) -> dict:
    if has_tag_ids:
        return {
            "course": tag_groups.get("课程"),
            "typeName": tag_groups.get("案例类型"),
            "stageText": case.get("stageText"),
            "audience": _audience_label(case.get("audience")),
            "purpose": case.get("purpose"),
            "theoryPoints": tag_groups.get("思政元素"),
        }
    # 旧种子案例仍以已有顶层字段展示；新案例的课程不走这条路径。
    values = {field: case.get(field) for field, _label in _COURSE_CONTEXT_FIELDS}
    values["audience"] = _audience_label(values["audience"])
    return values


def _tag_context_lines(tag_groups: dict, has_tag_ids: bool) -> list[str]:
    if tag_groups:
        return [
            "- 当前案例 tagIds 按现有标签组解析的名称：",
            *(
                f"- {group_name}：{_context_value(names)}"
                for group_name, names in tag_groups.items()
            ),
        ]
    if has_tag_ids:
        return ["- 当前案例 tagIds 未返回可用标签名称；缺失标签不得推断。"]
    return []


def _review_tag_lines(tag_groups: dict, has_tag_ids: bool) -> list[str]:
    """审核上下文只认真实已选标签：无标签时明示不足，不退回旧课程/受众字段。"""
    if tag_groups:
        return _tag_context_lines(tag_groups, has_tag_ids)
    if has_tag_ids:
        return ["- 当前案例 tagIds 未返回可用标签名称；缺失标签不得推断。"]
    return ["- 当前案例未选择任何标签：标签一致性与课堂适用性缺少依据，不得推断。"]


def _author_context_lines(case: dict, tag_groups: dict, has_tag_ids: bool) -> list[str]:
    values = _context_fields(case, tag_groups, has_tag_ids)
    lines = _tag_context_lines(tag_groups, has_tag_ids)
    lines.extend(
        f"- {label}：{_context_value(values[field])}"
        for field, label in _COURSE_CONTEXT_FIELDS
    )
    return lines


def _grounding_instructions(case: dict, database=None, review: bool = False) -> str:
    tag_groups = _tag_groups(database, case)
    has_tag_ids = bool(case.get("tagIds"))
    lines = [
        "## 服务端运行上下文",
        f"- 系统当前日期（北京时间，服务端提供）：{_current_date()}",
        "- 以下课程与案例标签来自当前案例服务端上下文，优先于 Skill 主题或模型记忆：",
    ]
    lines.extend(
        _review_tag_lines(tag_groups, has_tag_ids) if review
        else _author_context_lines(case, tag_groups, has_tag_ids)
    )
    return "\n".join(lines)


def _node_text(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    if isinstance(node.get("text"), str):
        return node["text"]
    return "".join(_node_text(child) for child in node.get("content", []))


def _role_prompts(reader: bool, review: bool) -> str:
    if review:
        return prompt_text("review-agent.md")
    if reader:
        return prompt_text("reader-agent.md")
    return "\n\n".join((prompt_text("case-agent.md"), prompt_text("revision-task.md")))


def case_instructions(
    case: dict, *, database=None, extra: str = "", reader: bool = False,
    review: bool = False,
) -> str:
    title = str(case.get("title") or "未命名案例")
    text = _node_text(case.get("document"))[:12000]
    prompts = _role_prompts(reader, review)
    base = "\n\n".join((
        prompts,
        prompt_text("grounding.md"),
        _grounding_instructions(case, database, review),
        f"当前案例标题：{title}",
        f"当前案例正文：{text}",
    ))
    return f"{base}\n\n{extra}" if extra else base
