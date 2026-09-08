"""结构化正文块：初稿写入的受控输入、存储与显示共用同一形状。

模型不得把 Markdown 标记当正文：标题、段落、列表和引用必须用块类型表达。
服务端校验后以规范化「输入形状」（text/items/paragraphs）存储与投影，
写入时才转换为 ProseMirror 节点；块类型按 type 字面值分发，避免子类
继承导致有序列表被折叠为无序列表。整篇写入仅允许真空文档或未编辑模板。
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
    """校验并返回规范化块（输入形状）；该形状同时用于存储、预览与遮蔽。"""
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
    # 按 type 字面值分发：ordered_list 是 bullet_list 的子类，
    # isinstance 顺序会把有序列表错归为无序列表。
    kind = getattr(block, "type", None)
    if kind == "heading":
        return {"type": "heading", "level": block.level, "text": block.text}
    if kind == "paragraph":
        return {"type": "paragraph", "text": block.text}
    if kind == "ordered_list":
        return {"type": "ordered_list", "items": list(block.items)}
    if kind == "bullet_list":
        return {"type": "bullet_list", "items": list(block.items)}
    assert isinstance(block, BlockquoteBlock)
    return {"type": "blockquote", "paragraphs": list(block.paragraphs)}


def structured_document(normalized_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """把规范化块转换为经过校验的 ProseMirror 文档（仅写入时）。"""
    return validate_prosemirror_document(
        {"type": "doc", "content": [_document_node(block) for block in normalized_blocks]}
    )


def _document_node(block: dict[str, Any]) -> dict[str, Any]:
    kind = block.get("type")
    if kind == "heading":
        return {"type": "heading", "attrs": {"level": block["level"]},
                "content": [_text_node(block["text"])]}
    if kind == "paragraph":
        return {"type": "paragraph", "content": [_text_node(block["text"])]}
    if kind in ("bullet_list", "ordered_list"):
        pm_kind = "bulletList" if kind == "bullet_list" else "orderedList"
        return {"type": pm_kind,
                "content": [_list_item(text) for text in block["items"]]}
    assert kind == "blockquote"
    return {"type": "blockquote",
            "content": [{"type": "paragraph", "content": [_text_node(text)]}
                        for text in block["paragraphs"]]}


def _text_node(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _list_item(text: str) -> dict[str, Any]:
    return {"type": "listItem",
            "content": [{"type": "paragraph", "content": [_text_node(text)]}]}


def document_blank(document: dict[str, Any]) -> bool:
    """真空文档：仅含空段落或纯空白且无任何 mark 的文本。

    hardBreak/citation 等原子内容与携带 mark 的文本都是内容，
    不得判空后整篇覆盖。
    """
    for node in document.get("content") or []:
        if node.get("type") != "paragraph":
            return False
        for child in node.get("content") or []:
            if child.get("type") != "text" or child.get("marks"):
                return False
            if str(child.get("text", "")).strip():
                return False
    return True


def document_rewritable(document: dict[str, Any]) -> bool:
    """整篇写入仅接受真空文档或未经改动的模板正文。"""
    return document_blank(document) or document == new_case_document()
