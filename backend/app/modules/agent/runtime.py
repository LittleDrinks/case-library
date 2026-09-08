from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic_ai import Agent


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
    ("audience", "适用对象代码"),
    ("purpose", "教学用途"),
    ("theoryPoints", "理论/思政要点"),
)


def prompt_text(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def _current_date() -> str:
    """Use the host-provided date instead of a model's internal date."""
    return date.today().isoformat()


def _case_value(case: dict, field: str):
    value = case.get(field)
    if value is None and isinstance(case.get("metadata"), dict):
        value = case["metadata"].get(field)
    return value


def _context_value(value: object) -> str:
    if value is None or value == "" or value == []:
        return "未提供（不得推断）"
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value) or "未提供（不得推断）"
    return str(value)


def _grounding_instructions(case: dict) -> str:
    lines = [
        "## 服务端运行上下文",
        f"- 系统当前日期（服务端提供）：{_current_date()}",
        "- 以下课程字段来自当前案例服务端元数据，优先于 Skill 主题或模型记忆：",
    ]
    lines.extend(
        f"- {label}：{_context_value(_case_value(case, field))}"
        for field, label in _COURSE_CONTEXT_FIELDS
    )
    return "\n".join(lines)


def _node_text(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    if isinstance(node.get("text"), str):
        return node["text"]
    return "".join(_node_text(child) for child in node.get("content", []))


def case_instructions(case: dict, *, extra: str = "", reader: bool = False) -> str:
    title = str(case.get("title") or "未命名案例")
    text = _node_text(case.get("document"))[:12000]
    prompts = prompt_text("reader-agent.md") if reader else "\n\n".join(
        (prompt_text("case-agent.md"), prompt_text("revision-task.md"))
    )
    base = "\n\n".join((
        prompts,
        prompt_text("grounding.md"),
        _grounding_instructions(case),
        f"当前案例标题：{title}",
        f"当前案例正文：{text}",
    ))
    return f"{base}\n\n{extra}" if extra else base
