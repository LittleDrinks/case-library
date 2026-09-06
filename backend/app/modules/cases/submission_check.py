"""投稿必填校验：标题、正文与必填标签组。

标签契约归 Issue 101：案例携带 `tagIds`（稳定标签 ID 列表），
必填组校验直接调用 tags 模块的 validate_submission_tags，
本模块不定义第二套标签结构。
"""
from __future__ import annotations

from pymongo.database import Database

from app.modules.tags.service import validate_submission_tags


def document_text(document: dict) -> str:
    values, stack = [], [document]
    while stack:
        node = stack.pop()
        if node.get("type") == "text":
            values.append(node["text"])
        stack.extend(reversed(node.get("content", [])))
    return "".join(values)


def submission_issues(database: Database, case: dict) -> list[str]:
    issues = _content_issues(case)
    issues.extend(_tag_issues(database, case))
    return issues


def _content_issues(case: dict) -> list[str]:
    issues = []
    if not str(case.get("title") or "").strip():
        issues.append("标题不能为空")
    if not document_text(case.get("document") or {}).strip():
        issues.append("正文不能为空")
    return issues


def _tag_issues(database: Database, case: dict) -> list[str]:
    missing = validate_submission_tags(database, case.get("tagIds") or [])
    return [f"必填标签组未选择标签：{group['name']}" for group in missing]
