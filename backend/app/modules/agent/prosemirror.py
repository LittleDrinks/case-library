"""服务端正文段落结构与修订范围校验：目标段落的解析、校验与替换。"""

from __future__ import annotations

from typing import Any

from app.modules.cases.document_schema import validate_prosemirror_document


class ParagraphNotFoundError(Exception):
    pass


class ParagraphChangedError(Exception):
    pass


def _node_text(node: dict[str, Any]) -> str:
    if node.get("type") == "hardBreak":
        return "\n"
    if node.get("type") != "text":
        return "".join(_node_text(child) for child in node.get("content", []))
    return node.get("text", "")


def paragraphs(document: dict[str, Any]) -> list[dict[str, Any]]:
    """按出现顺序返回正文顶层段落的编号与原文。"""
    return [
        {"paragraphIndex": index, "quote": _node_text(node)}
        for index, node in enumerate(document.get("content", []))
        if node.get("type") == "paragraph"
    ]


def _match_target(document: dict[str, Any], paragraph_index: int, quote: str) -> dict:
    rows = paragraphs(document)
    if paragraph_index >= len(rows):
        raise ParagraphNotFoundError
    target = rows[paragraph_index]
    if target["quote"] != quote:
        raise ParagraphChangedError
    return target


def check_target(document: dict[str, Any], paragraph_index: int, quote: str) -> None:
    """重验目标段落仍然存在且原文未变，否则抛出对应异常。"""
    _match_target(document, paragraph_index, quote)


def replaced_document(
    document: dict[str, Any], paragraph_index: int, quote: str, replacement: str
) -> dict[str, Any]:
    """返回目标段落文本替换后的新文档，替换前重验编号与原文。"""
    _match_target(document, paragraph_index, quote)
    position, content = 0, list(document.get("content", []))
    for index, node in enumerate(content):
        if node.get("type") == "paragraph":
            if position == paragraph_index:
                content[index] = _replaced_node(node, replacement)
                break
            position += 1
    updated = {**document, "content": content}
    validate_prosemirror_document(updated)
    return updated


def _replaced_node(node: dict[str, Any], replacement: str) -> dict[str, Any]:
    if not replacement:
        return {"type": "paragraph", "content": []}
    return {"type": "paragraph", "content": [{"type": "text", "text": replacement}]}
