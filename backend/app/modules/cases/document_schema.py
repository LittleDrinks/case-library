from __future__ import annotations

import json
from typing import Any

MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_DOCUMENT_DEPTH = 20
MAX_DOCUMENT_NODES = 5000
BLOCK_NODES = {"paragraph", "heading", "bulletList", "orderedList", "blockquote"}
INLINE_NODES = {"text", "hardBreak"}
LIST_NODES = {"bulletList", "orderedList"}
ALLOWED_NODES = BLOCK_NODES | INLINE_NODES | {"doc", "listItem"}
ALLOWED_MARKS = {"bold", "italic", "strike", "citation"}
CITATION_SOURCE_TYPES = {"case", "material", "attachment"}
MAX_SOURCE_ID = 120
REQUIRED_CONTENT = LIST_NODES | {"blockquote", "listItem"}
NODE_KEYS = {
    "doc": {"type", "content"},
    "paragraph": {"type", "content"},
    "heading": {"type", "attrs", "content"},
    "text": {"type", "text", "marks"},
    "bulletList": {"type", "content"},
    "orderedList": {"type", "attrs", "content"},
    "listItem": {"type", "content"},
    "blockquote": {"type", "content"},
    "hardBreak": {"type"},
}


def citation_refs(document: dict[str, Any]) -> list[dict[str, str]]:
    """按出现顺序收集去重后的 citation 引用对。"""
    refs: list[dict[str, str]] = []
    stack = [document]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        for mark in node.get("marks", []):
            if isinstance(mark, dict) and mark.get("type") == "citation":
                ref = mark.get("attrs", {})
                pair = {"sourceType": ref.get("sourceType"), "sourceId": ref.get("sourceId")}
                if pair not in refs:
                    refs.append(pair)
        stack.extend(reversed(node.get("content", [])))
    return refs


def _document_size(document: dict[str, Any]) -> int:
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    return len(encoded.encode("utf-8"))


def _node_kind(node: Any) -> str:
    if not isinstance(node, dict):
        raise ValueError("ProseMirror 节点必须是对象")
    kind = node.get("type")
    if not isinstance(kind, str) or kind not in ALLOWED_NODES:
        raise ValueError(f"未知节点：{kind}")
    return kind


def _validate_keys(node: dict, kind: str) -> None:
    unknown = set(node) - NODE_KEYS[kind]
    if unknown:
        raise ValueError(f"{kind} 包含未知字段：{sorted(unknown)[0]}")


def _validate_attrs(node: dict, kind: str) -> None:
    attrs = node.get("attrs")
    if kind == "heading":
        if not isinstance(attrs, dict) or set(attrs) != {"level"}:
            raise ValueError("heading.attrs 只能包含 level")
        level = attrs["level"]
        if isinstance(level, bool) or level not in {1, 2, 3}:
            raise ValueError("heading.level 必须是 1、2 或 3")
    if kind == "orderedList" and attrs is not None:
        if not isinstance(attrs, dict) or set(attrs) != {"start"}:
            raise ValueError("orderedList.attrs 只能包含 start")
        start = attrs["start"]
        if isinstance(start, bool) or not isinstance(start, int) or start < 1:
            raise ValueError("orderedList.start 必须是正整数")


def _validate_mark(mark: Any) -> str:
    if not isinstance(mark, dict):
        raise ValueError("mark 必须是对象")
    mark_type = mark.get("type")
    if not isinstance(mark_type, str) or mark_type not in ALLOWED_MARKS:
        raise ValueError(f"未知 mark：{mark_type}")
    if mark_type == "citation":
        _validate_citation_attrs(mark)
    elif set(mark) != {"type"}:
        raise ValueError("mark 只能包含 type")
    return mark_type


def _validate_citation_attrs(mark: dict) -> None:
    if set(mark) != {"type", "attrs"} or not isinstance(mark.get("attrs"), dict):
        raise ValueError("citation mark 只能包含 type 和 attrs")
    attrs = mark["attrs"]
    if set(attrs) != {"sourceType", "sourceId"}:
        raise ValueError("citation attrs 只能包含 sourceType 和 sourceId")
    if attrs["sourceType"] not in CITATION_SOURCE_TYPES:
        raise ValueError("citation sourceType 必须是 case、material 或 attachment")
    source_id = attrs["sourceId"]
    if not isinstance(source_id, str) or not 1 <= len(source_id) <= MAX_SOURCE_ID:
        raise ValueError("citation sourceId 必须是 1-120 个字符")


def _validate_text(node: dict) -> None:
    if not isinstance(node.get("text"), str) or not node["text"]:
        raise ValueError("text.text 必须是非空字符串")
    marks = node.get("marks", [])
    if not isinstance(marks, list):
        raise ValueError("text.marks 必须是数组")
    mark_types = [_validate_mark(mark) for mark in marks]
    if len(mark_types) != len(set(mark_types)):
        raise ValueError("text.marks 不能重复")


def _content(node: dict, kind: str) -> list[dict]:
    if kind in INLINE_NODES:
        return []
    if kind == "doc" and "content" not in node:
        raise ValueError("doc.content 必须是数组")
    content = node.get("content", [])
    if not isinstance(content, list):
        raise ValueError(f"{kind}.content 必须是数组")
    if kind in REQUIRED_CONTENT and not content:
        raise ValueError(f"{kind}.content 不能为空")
    return content


def _allowed_children(kind: str, index: int) -> set[str]:
    if kind in {"doc", "blockquote"}:
        return BLOCK_NODES
    if kind in {"paragraph", "heading"}:
        return INLINE_NODES
    if kind in LIST_NODES:
        return {"listItem"}
    if kind == "listItem":
        return {"paragraph"} if index == 0 else BLOCK_NODES
    return set()


def _validate_children(kind: str, children: list[dict]) -> None:
    for index, child in enumerate(children):
        child_kind = _node_kind(child)
        if child_kind not in _allowed_children(kind, index):
            raise ValueError(f"{kind} 不能包含 {child_kind}")


def _validate_node(node: Any) -> list[dict]:
    kind = _node_kind(node)
    _validate_keys(node, kind)
    _validate_attrs(node, kind)
    if kind == "text":
        _validate_text(node)
    children = _content(node, kind)
    _validate_children(kind, children)
    return children


def validate_prosemirror_document(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "doc":
        raise ValueError("document 必须是 ProseMirror doc JSON")
    if _document_size(value) > MAX_DOCUMENT_BYTES:
        raise ValueError("document 不能超过 1MiB")
    stack: list[tuple[Any, int]] = [(value, 1)]
    count = 0
    while stack:
        node, depth = stack.pop()
        if depth > MAX_DOCUMENT_DEPTH:
            raise ValueError("document 深度不能超过 20")
        count += 1
        if count > MAX_DOCUMENT_NODES:
            raise ValueError("document 节点不能超过 5000")
        stack.extend((child, depth + 1) for child in _validate_node(node))
    return value


def validate_optional_document(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return validate_prosemirror_document(value) if value is not None else None
