from __future__ import annotations

from copy import deepcopy


def _heading(text: str, level: int) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _paragraph(text: str = "") -> dict:
    content = [{"type": "text", "text": text}] if text else []
    return {"type": "paragraph", "content": content}


CASE_DOCUMENT_TEMPLATE = {
    "type": "doc",
    "content": [
        _heading("一、教学说明（800字左右）", 1),
        _heading("（一）教学目的", 2),
        _paragraph(),
        _heading("（二）阅读思考题（2～3个）", 2),
        _paragraph(),
        _heading("（三）教学安排", 2),
        _paragraph(),
        _heading("（四）注意事项", 2),
        _paragraph("课前阅读材料；分组讨论；小组代表发表核心观点"),
        _heading("二、文本内容（2500字左右）", 1),
        _paragraph("（要求：主题鲜明，逻辑清晰，结构合理，文字流畅）"),
        _heading("三、附件", 1),
        _paragraph("推荐阅读书目和备课主要参考书（若有，5本左右）"),
    ],
}


def new_case_document() -> dict:
    return deepcopy(CASE_DOCUMENT_TEMPLATE)
