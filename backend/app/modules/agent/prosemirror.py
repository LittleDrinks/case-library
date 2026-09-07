"""服务端正文选区校验与范围替换：ProseMirror 文档位置契约。

选区以绝对文档位置 from/to 表达，前后端对同一文档版本解析；服务端按
官方位置规则（内容自进入位置 +1 起、非叶子 nodeSize = 内容 +2）定位
文本块并核对选区原文，接受时只替换选中范围，保留其余内容与标记。
"""

from __future__ import annotations

from typing import Any

from app.modules.cases.document_schema import validate_prosemirror_document


class ParagraphNotFoundError(Exception):
    pass


class ParagraphChangedError(Exception):
    pass


def _node_size(node: dict[str, Any]) -> int:
    if node.get("type") == "text":
        return len(node.get("text", ""))
    if "content" in node:
        return sum(_node_size(child) for child in node["content"]) + 2
    return 1


def _is_block_content(children: list[dict[str, Any]]) -> bool:
    return any("content" in child for child in children)


def text_blocks(document: dict[str, Any]) -> list[dict[str, Any]]:
    """返回每个文本块的绝对内容范围 [start, end)；块内文本用 text_between。"""
    blocks: list[dict[str, Any]] = []
    _collect_blocks(document.get("content", []), 0, blocks)
    return blocks


def _collect_blocks(nodes: list[dict[str, Any]], offset: int, blocks: list) -> None:
    position = offset
    for node in nodes:
        size = _node_size(node)
        children = node.get("content")
        if children and _is_block_content(children):
            _collect_blocks(children, position + 1, blocks)
        elif children:
            blocks.append({"start": position + 1, "end": position + size - 1})
        position += size


def text_between(document: dict[str, Any], from_pos: int, to_pos: int) -> str:
    """选区范围内的纯文本：文本节点按交集切片，硬换行计为换行符。"""
    parts: list[str] = []
    _collect_text(document.get("content", []), 0, from_pos, to_pos, parts)
    return "".join(parts)


def _collect_text(nodes: list[dict[str, Any]], offset: int, from_pos: int,
                  to_pos: int, parts: list[str]) -> None:
    position = offset
    for node in nodes:
        size = _node_size(node)
        start, end = position, position + size
        if node.get("type") == "text" and start < to_pos and end > from_pos:
            lo, hi = max(start, from_pos), min(end, to_pos)
            parts.append(node.get("text", "")[lo - start:hi - start])
        elif node.get("type") == "hardBreak" and start >= from_pos and end <= to_pos:
            parts.append("\n")
        if node.get("content"):
            _collect_text(node["content"], start + 1, from_pos, to_pos, parts)
        position = end


def selection_block(document: dict[str, Any], from_pos: int, to_pos: int) -> dict:
    """返回完整包含 [from,to) 的文本块；空选区、跨块或越界抛 ParagraphNotFoundError。"""
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
    """重验选区仍位于同一文本块且原文未变，否则抛出对应异常。"""
    selection_block(document, from_pos, to_pos)
    if text_between(document, from_pos, to_pos) != quote:
        raise ParagraphChangedError


def replaced_document(
    document: dict[str, Any], from_pos: int, to_pos: int, quote: str, replacement: str
) -> dict[str, Any]:
    """只替换 [from,to) 范围文本，保留未选内容与标记；替换前重验选区。"""
    check_target(document, from_pos, to_pos, quote)
    updated = {
        **document,
        "content": _replace_nodes(
            document.get("content", []), 0, from_pos, to_pos, replacement
        ),
    }
    validate_prosemirror_document(updated)
    return updated


def _replace_nodes(nodes: list[dict[str, Any]], offset: int, from_pos: int,
                   to_pos: int, replacement: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    position = offset
    for node in nodes:
        result.append(_replaced_node_at(node, position, from_pos, to_pos, replacement))
        position += _node_size(node)
    return result


def _replaced_node_at(node: dict[str, Any], start: int, from_pos: int,
                      to_pos: int, replacement: str) -> dict[str, Any]:
    children = node.get("content")
    contains = start + 1 <= from_pos and to_pos <= start + _node_size(node) - 1
    if children is None or not contains:
        return node
    if _is_block_content(children):
        inner = _replace_nodes(children, start + 1, from_pos, to_pos, replacement)
    else:
        inner = _replace_inline(children, start + 1, from_pos, to_pos, replacement)
    return {**node, "content": inner}


def _replace_inline(nodes: list[dict[str, Any]], offset: int, from_pos: int,
                    to_pos: int, replacement: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    position = offset
    inserted = False
    for node in nodes:
        start = position
        end = position + _node_size(node)
        position = end
        if end <= from_pos or start >= to_pos:
            result.append(node)
            continue
        inserted = _replace_overlap(
            result, node, start, end, from_pos, to_pos, replacement, inserted
        )
    return result


def _replace_overlap(result: list, node: dict[str, Any], start: int, end: int,
                     from_pos: int, to_pos: int, replacement: str,
                     inserted: bool) -> bool:
    if node.get("type") == "text" and start < from_pos:
        result.append(_text_slice(node, start, start, from_pos))
    if not inserted:
        inserted = True
        if replacement:
            result.append({"type": "text", "text": replacement})
    if node.get("type") == "text" and end > to_pos:
        result.append(_text_slice(node, start, to_pos, end))
    return inserted


def _text_slice(node: dict[str, Any], node_start: int, cut_from: int, cut_to: int) -> dict:
    return {
        **{k: v for k, v in node.items() if k != "text"},
        "text": node.get("text", "")[cut_from - node_start:cut_to - node_start],
    }
