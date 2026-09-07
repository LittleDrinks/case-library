"""结构化正文块：初稿写入的受控输入与服务端规范化。

模型不得把 Markdown 标记当正文：标题、段落、列表和引用必须用块类型表达，
服务端校验并转换为 ProseMirror 文档；整篇写入仅允许空草稿或模板。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from app.modules.cases.document_schema import validate_prosemirror_document
from app.modules.cases.service import CaseError
from app.modules.cases.template import new_case_document

MAX_BLOCKS = 300
MAX_BLOCK_TEXT = 10_000
MAX_LIST_ITEMS = 50


def _clean_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("文本不能为空")
    if len(text) > MAX_BLOCK_TEXT:
        raise ValueError("单块文本过长")
    return text


class ParagraphBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["paragraph"]
    text: str

    _clean = field_validator("text")(_clean_text)


class HeadingBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["heading"]
    level: int = Field(ge=1, le=3)
    text: str

    _clean = field_validator("text")(_clean_text)


class BulletListBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["bullet_list"]
    items: list[str] = Field(min_length=1, max_length=MAX_LIST_ITEMS)

    _clean = field_validator("items")(lambda values: [_clean_text(value) for value in values])


class OrderedListBlock(BulletListBlock):
    type: Literal["ordered_list"]


class BlockquoteBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["blockquote"]
    paragraphs: list[str] = Field(min_length=1, max_length=MAX_LIST_ITEMS)

    _clean = field_validator("paragraphs")(
        lambda values: [_clean_text(value) for value in values]
    )


_BLOCK_ADAPTER: TypeAdapter = TypeAdapter(
    Annotated[
        ParagraphBlock | HeadingBlock | BulletListBlock | OrderedListBlock | BlockquoteBlock,
        Field(discriminator="type"),
    ]
)


def validate_blocks(blocks: object) -> list[dict[str, Any]]:
    """校验并规范化正文块；输入不合法时抛出可重试的 CaseError。"""
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS:
        raise CaseError(422, "正文块无效：需要 1-300 个块")
    normalized: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        try:
            model = _BLOCK_ADAPTER.validate_python(block)
        except ValidationError as error:
            raise CaseError(422, f"第 {index + 1} 个正文块无效") from error
        normalized.append(_normalized(model))
    return normalized


def _normalized(block: object) -> dict[str, Any]:
    if isinstance(block, HeadingBlock):
        return {"type": "heading", "attrs": {"level": block.level},
                "content": [_text_node(block.text)]}
    if isinstance(block, ParagraphBlock):
        return {"type": "paragraph", "content": [_text_node(block.text)]}
    if isinstance(block, BulletListBlock):
        return {"type": "bulletList",
                "content": [_list_item(text) for text in block.items]}
    if isinstance(block, OrderedListBlock):
        return {"type": "orderedList",
                "content": [_list_item(text) for text in block.items]}
    assert isinstance(block, BlockquoteBlock)
    return {"type": "blockquote",
            "content": [{"type": "paragraph", "content": [_text_node(text)]}
                        for text in block.paragraphs]}


def _text_node(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _list_item(text: str) -> dict[str, Any]:
    return {"type": "listItem",
            "content": [{"type": "paragraph", "content": [_text_node(text)]}]}


def structured_document(normalized_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """把规范化正文块转换为经过校验的 ProseMirror 文档。"""
    return validate_prosemirror_document({"type": "doc", "content": normalized_blocks})


def _node_text(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if isinstance(node.get("text"), str):
        return node["text"]
    return "".join(_node_text(child) for child in node.get("content", []))


def document_text(document: dict[str, Any]) -> str:
    return _node_text(document)


def document_blank(document: dict[str, Any]) -> bool:
    return not document_text(document).strip()


def document_rewritable(document: dict[str, Any]) -> bool:
    """整篇写入仅接受空草稿或未经改动的模板正文。"""
    return document_blank(document) or document == new_case_document()


def block_lines(normalized_blocks: list[dict[str, Any]]) -> list[str]:
    """把规范化正文块压平为纯文本行，供选区范围内的直接写入使用。"""
    lines: list[str] = []
    for block in normalized_blocks:
        kind = block.get("type")
        if kind in ("bulletList", "orderedList"):
            lines.extend(_node_text(item) for item in block.get("content", []))
        elif kind == "blockquote":
            lines.extend(
                _node_text(paragraph) for paragraph in block.get("content", [])
            )
        else:
            lines.append(_node_text(block))
    return [line for line in lines if line]
