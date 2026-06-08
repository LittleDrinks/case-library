"""Prompt registry for server-side AI self-check workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    id: str
    name: str
    description: str
    category: str
    variables: tuple[str, ...]
    content: str
    output_schema: str | None = None

    def metadata(self) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "variables": list(self.variables),
        }
        if self.output_schema:
            data["output_schema"] = self.output_schema
        return data


_JSON_RULE = (
    "只返回一个 JSON 对象，不要使用 Markdown。"
    "字段至少包含 pass(boolean)、detail(string)、suggestions(array)。"
)


PROMPTS: dict[str, Prompt] = {
    "workflow/completeness": Prompt(
        id="workflow/completeness",
        name="完整性检查",
        description="检查案例是否包含背景、做法、成效与反思等关键板块",
        category="workflow",
        variables=("title", "content"),
        output_schema="json",
        content=(
            "你是高校思政案例库的提交前自查助手。请检查案例《{title}》的内容完整性。"
            "重点判断是否包含教学背景、问题分析、实施过程、育人成效和改进反思。"
            f"{_JSON_RULE}\n\n案例内容：\n{{content}}"
        ),
    ),
    "workflow/categorization": Prompt(
        id="workflow/categorization",
        name="分类检查",
        description="检查案例类型和主题是否与正文内容匹配",
        category="workflow",
        variables=("title", "content", "type", "theme"),
        output_schema="json",
        content=(
            "你是高校思政案例库的分类自查助手。请判断案例《{title}》的类型"
            "「{type}」和主题「{theme}」是否匹配正文内容，并指出明显偏差。"
            f"{_JSON_RULE}\n\n案例内容：\n{{content}}"
        ),
    ),
    "workflow/expression": Prompt(
        id="workflow/expression",
        name="表达检查",
        description="检查案例表达是否清晰、正式、适合专家审核",
        category="workflow",
        variables=("title", "content"),
        output_schema="json",
        content=(
            "你是高校思政案例库的文本表达自查助手。请检查案例《{title}》"
            "是否表述清晰、结构正式、避免口语化，并给出简洁修改建议。"
            f"{_JSON_RULE}\n\n案例内容：\n{{content}}"
        ),
    ),
    "workflow/score": Prompt(
        id="workflow/score",
        name="综合评分",
        description="给出提交前综合自查评分和主要风险",
        category="workflow",
        variables=("title", "content"),
        output_schema="json",
        content=(
            "你是高校思政案例库的提交前综合自查助手。请对案例《{title}》"
            "给出 0-100 的自查评分、主要风险和优先修改建议。"
            "只返回一个 JSON 对象，不要使用 Markdown。字段至少包含 "
            "pass(boolean)、score(number)、detail(string)、suggestions(array)。"
            "\n\n案例内容：\n{content}"
        ),
    ),
}


def get_prompt(prompt_id: str) -> Prompt | None:
    return PROMPTS.get(prompt_id)


def list_prompt_metadata(category: str | None = None) -> list[dict]:
    if not category:
        return []
    return [prompt.metadata() for prompt in PROMPTS.values() if prompt.category == category]
