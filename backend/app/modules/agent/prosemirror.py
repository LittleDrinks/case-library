"""ProseMirror selection validation and native range replacement."""

from __future__ import annotations

from typing import Any

from prosemirror.model import Schema
from prosemirror.transform import Transform

from app.modules.cases.document_schema import validate_prosemirror_document


class ParagraphNotFoundError(Exception):
    pass


class ParagraphChangedError(Exception):
    pass


_SCHEMA = Schema({
    "nodes": {
        "doc": {"content": "block*"},
        "paragraph": {"content": "inline*", "group": "block"},
        "heading": {
            "attrs": {"level": {"validate": "number"}},
            "content": "inline*", "group": "block",
        },
        "blockquote": {"content": "block+", "group": "block"},
        "bulletList": {"content": "listItem+", "group": "block"},
        "orderedList": {
            "attrs": {"start": {"default": 1, "validate": "number"}},
            "content": "listItem+", "group": "block",
        },
        "listItem": {"content": "paragraph block*"},
        "text": {"group": "inline"},
        "hardBreak": {
            "inline": True, "group": "inline", "selectable": False,
            "leafText": lambda _node: "\n",
        },
    },
    "marks": {"bold": {}, "italic": {}, "strike": {}},
})


def _document(value: dict[str, Any]):
    validate_prosemirror_document(value)
    return _SCHEMA.node_from_json(value)


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


def text_blocks(document: dict[str, Any]) -> list[dict[str, int]]:
    """Return native ProseMirror content ranges for every text block."""
    blocks: list[dict[str, int]] = []
    _document(document).descendants(
        lambda node, pos, _parent, _index: blocks.append(
            {"start": pos + 1, "end": pos + 1 + node.content.size}
        ) if node.is_textblock else None
    )
    return blocks


def text_between(document: dict[str, Any], from_pos: int, to_pos: int) -> str:
    """Read a native ProseMirror range, including hard breaks as newlines."""
    return _document(document).text_between(from_pos, to_pos, leaf_text="\n")


def selection_block(document: dict[str, Any], from_pos: int, to_pos: int) -> dict:
    """Return the text block containing a non-empty range."""
    if from_pos >= to_pos:
        raise ParagraphNotFoundError
    block = next(
        (row for row in text_blocks(document)
         if row["start"] <= from_pos and to_pos <= row["end"]),
        None,
    )
    if block is None:
        raise ParagraphNotFoundError
    return block


def check_target(document: dict[str, Any], from_pos: int, to_pos: int, quote: str) -> None:
    """Recheck the native range and its original text."""
    selection_block(document, from_pos, to_pos)
    if text_between(document, from_pos, to_pos) != quote:
        raise ParagraphChangedError


def replaced_document(
    document: dict[str, Any], from_pos: int, to_pos: int, quote: str, replacement: str
) -> dict[str, Any]:
    """Replace only a checked range with a native ProseMirror transform."""
    check_target(document, from_pos, to_pos, quote)
    content = _SCHEMA.text(replacement) if replacement else []
    updated = Transform(_document(document)).replace_with(
        from_pos, to_pos, content
    ).doc.to_json()
    validate_prosemirror_document(updated)
    return updated
