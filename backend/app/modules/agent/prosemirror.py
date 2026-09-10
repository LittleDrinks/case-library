"""ProseMirror selection validation and native range replacement."""

from __future__ import annotations

from typing import Any

from prosemirror.model import Schema
from prosemirror.model import Slice
from prosemirror.transform import Step, Transform

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
    "marks": {"bold": {}, "italic": {}, "strike": {},
              "citation": {
                  "attrs": {
                      "sourceType": {"validate": "string"},
                      "sourceId": {"validate": "string"},
                  },
              }},
})


def _document(value: dict[str, Any]):
    validate_prosemirror_document(value)
    return _SCHEMA.node_from_json(value)


def _result(transform: Transform) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = transform.doc.to_json()
    document.setdefault("content", [])
    validate_prosemirror_document(document)
    return document, [step.to_json() for step in transform.steps]


def replace_document(document: dict[str, Any], updated: dict[str, Any]):
    source, target = _document(document), _document(updated)
    transform = Transform(source).replace(0, source.content.size, Slice(target.content, 0, 0))
    return _result(transform)


def apply_steps(document: dict[str, Any], steps: list[dict[str, Any]]):
    transform = Transform(_document(document))
    for raw in steps:
        result = transform.maybe_step(Step.from_json(_SCHEMA, raw))
        if result.failed:
            raise ValueError(result.failed)
    applied, _steps = _result(transform)
    return applied, transform.mapping


def invert_steps(document: dict[str, Any], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source, inverted = _document(document), []
    for raw in steps:
        step = Step.from_json(_SCHEMA, raw)
        inverted.append(step.invert(source).to_json())
        result = step.apply(source)
        if result.failed:
            raise ValueError(result.failed)
        source = result.doc
    return list(reversed(inverted))


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


def replaced_document_with_steps(
    document: dict[str, Any], from_pos: int, to_pos: int, quote: str, replacement: str
):
    check_target(document, from_pos, to_pos, quote)
    content = _SCHEMA.text(replacement) if replacement else []
    return _replace(document, from_pos, to_pos, content)


def _replace(document: dict[str, Any], from_pos: int, to_pos: int, content):
    return _result(Transform(_document(document)).replace_with(from_pos, to_pos, content))


def replaced_document_blocks_with_steps(
    document: dict[str, Any], from_pos: int, to_pos: int, quote: str,
    block_nodes: list[dict[str, Any]],
):
    check_target(document, from_pos, to_pos, quote)
    block = selection_block(document, from_pos, to_pos)
    if from_pos == block["start"] and to_pos == block["end"]:
        from_pos, to_pos = block["start"] - 1, block["end"] + 1
    nodes = [_SCHEMA.node_from_json(node) for node in block_nodes]
    return _replace(document, from_pos, to_pos, nodes)
