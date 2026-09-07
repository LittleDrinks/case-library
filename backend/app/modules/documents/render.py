from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from app.modules.cases.document_schema import validate_prosemirror_document
from app.modules.documents.fonts import embed_title_font
from app.modules.documents.styles import (
    BODY_FONT,
    BODY_SIZE,
    HEADING_FONT,
    HEADING_SIZE,
    TITLE_FONT,
    TITLE_SIZE,
    configure_document,
    format_body,
    format_heading,
    format_title,
    set_run_font,
)

LOGO_PATH = (
    Path(__file__).with_name("assets") / "shanghai-university-horizontal-logo.png"
)


def _mark_types(node: dict) -> set[str]:
    return {mark.get("type", "") for mark in node.get("marks", [])}


def _citation_key(node: dict) -> tuple[str | None, str | None] | None:
    for mark in node.get("marks", []):
        if mark.get("type") != "citation":
            continue
        attrs = mark.get("attrs", {})
        return (attrs.get("sourceType"), attrs.get("sourceId"))
    return None


def _inline_atoms(
    nodes: list[dict],
) -> list[tuple[str | None, dict | None, tuple[str | None, str | None] | None]]:
    """拍平内联节点；硬换行与嵌套边界切断引用标记的连续区间。"""
    atoms: list[
        tuple[str | None, dict | None, tuple[str | None, str | None] | None]
    ] = []
    for node in nodes:
        if node.get("type") == "hardBreak":
            atoms.append(("", None, None))
        elif node.get("type") == "text":
            atoms.append((str(node.get("text", "")), node, _citation_key(node)))
        elif node.get("content"):
            atoms.append((None, None, None))
            atoms.extend(_inline_atoms(node["content"]))
            atoms.append((None, None, None))
    return atoms


def _add_citation_run(paragraph: Paragraph, number: int, font: str, size: int) -> None:
    run = paragraph.add_run(f"〔{number}〕")
    set_run_font(run, font, size)
    run.font.superscript = True


def _format_marks(run: Run, node: dict) -> None:
    marks = _mark_types(node)
    run.bold = "bold" in marks
    run.italic = "italic" in marks
    run.font.strike = "strike" in marks


def _add_inlines(
    paragraph: Paragraph, nodes: list[dict], font: str, size: int, numbers: dict
) -> None:
    atoms = _inline_atoms(nodes)
    for index, (text, node, key) in enumerate(atoms):
        if text is None:
            continue
        if not text:
            paragraph.add_run().add_break()
            continue
        run = paragraph.add_run(text)
        set_run_font(run, font, size)
        _format_marks(run, node)
        # 相邻同引用属性的文本（即使加粗/斜体不同）只产生一个上标标记。
        runs_on = index + 1 < len(atoms) and atoms[index + 1][2] == key
        if key is None or runs_on:
            continue
        number = numbers.get(key)
        if number is not None: _add_citation_run(paragraph, number, font, size)


def _add_title(document: DocxDocument, title: str) -> None:
    paragraph = document.add_paragraph(style="Title")
    format_title(paragraph)
    run = paragraph.add_run(title)
    set_run_font(run, TITLE_FONT, TITLE_SIZE)


def _add_logo(document: DocxDocument) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(10)
    shape = paragraph.add_run().add_picture(str(LOGO_PATH), width=Mm(60))
    shape._inline.docPr.set("descr", "上海大学校徽")


def _add_heading(document: DocxDocument, node: dict, numbers: dict) -> None:
    level = min(3, max(1, int(node.get("attrs", {}).get("level", 1))))
    paragraph = document.add_paragraph(style=f"Heading {level}")
    format_heading(paragraph)
    _add_inlines(paragraph, node.get("content", []), HEADING_FONT, HEADING_SIZE, numbers)


def _add_paragraph(
    document: DocxDocument, node: dict, numbers: dict, style: str | None = None
) -> Paragraph:
    paragraph = document.add_paragraph(style=style)
    format_body(paragraph, indented=style is None)
    _add_inlines(paragraph, node.get("content", []), BODY_FONT, BODY_SIZE, numbers)
    return paragraph


def _bind_numbering(paragraph: Paragraph, num_id: int) -> None:
    properties = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    properties.get_or_add_ilvl().val = 0
    properties.get_or_add_numId().val = num_id


def _new_numbering(document: DocxDocument, style: str, start: int) -> int:
    style_num = document.styles[style].element.pPr.numPr.numId.val
    numbering = document.part.numbering_part.element
    abstract_num = numbering.num_having_numId(style_num).abstractNumId.val
    instance = numbering.add_num(abstract_num)
    if start != 1:
        instance.add_lvlOverride(ilvl=0).add_startOverride(val=start)
    return instance.numId


def _add_list(
    document: DocxDocument,
    node: dict,
    style: str,
    numbers: dict,
    num_id: int | None = None,
) -> None:
    for item in node.get("content", []):
        children = item.get("content", [])
        for index, child in enumerate(children):
            if child.get("type") == "paragraph":
                paragraph = _add_paragraph(
                    document, child, numbers, style if index == 0 else None
                )
                if index == 0 and num_id is not None:
                    _bind_numbering(paragraph, num_id)
            else:
                _add_node(document, child, numbers)


def _add_blockquote(document: DocxDocument, node: dict, numbers: dict) -> None:
    for child in node.get("content", []):
        if child.get("type") == "paragraph":
            _add_paragraph(document, child, numbers, "Quote")
        else:
            _add_node(document, child, numbers)


def _add_node(document: DocxDocument, node: dict, numbers: dict) -> None:
    kind = node.get("type")
    if kind == "heading":
        _add_heading(document, node, numbers)
    elif kind == "paragraph":
        _add_paragraph(document, node, numbers)
    elif kind == "blockquote":
        _add_blockquote(document, node, numbers)
    elif kind == "bulletList":
        _add_list(document, node, "List Bullet", numbers)
    elif kind == "orderedList":
        start = int(node.get("attrs", {}).get("start", 1))
        _add_list(
            document,
            node,
            "List Number",
            numbers,
            _new_numbering(document, "List Number", start),
        )


def _citation_numbers(entries: list[dict]) -> dict:
    return {(entry["sourceType"], entry["id"]): entry["number"] for entry in entries}


def _add_hyperlink(paragraph: Paragraph, url: str, text: str) -> None:
    relation = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), relation)
    run = OxmlElement("w:r")
    run.append(_link_style())
    value = OxmlElement("w:t")
    value.text = text
    run.append(value)
    link.append(run)
    paragraph._p.append(link)


def _link_style() -> OxmlElement:
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(color)
    properties.append(underline)
    return properties


def _reference_line(paragraph: Paragraph, entry: dict) -> None:
    label = f"〔{entry['number']}〕 {entry['title']}"
    if entry.get("source"):
        label += f"．{entry['source']}"
    if entry.get("version"):
        label += f"．{entry['version']}"
    run = paragraph.add_run(label)
    set_run_font(run, BODY_FONT, BODY_SIZE)
    if entry.get("url"):
        paragraph.add_run("．")
        _add_hyperlink(paragraph, entry["url"], "链接")


def _add_references(document: DocxDocument, entries: list[dict]) -> None:
    if not entries:
        return
    paragraph = document.add_paragraph(style="Heading 1")
    format_heading(paragraph)
    run = paragraph.add_run("参考资料")
    set_run_font(run, HEADING_FONT, HEADING_SIZE)
    for entry in entries:
        line = document.add_paragraph()
        format_body(line)
        _reference_line(line, entry)


def build_case_docx(case: dict, entries: list[dict]) -> bytes:
    validate_prosemirror_document(case["document"])
    numbers = _citation_numbers(entries)
    document = Document()
    configure_document(document)
    document.core_properties.title = str(case["title"])
    _add_logo(document)
    _add_title(document, str(case["title"]))
    for node in case["document"].get("content", []):
        _add_node(document, node, numbers)
    _add_references(document, entries)
    buffer = BytesIO()
    document.save(buffer)
    return embed_title_font(buffer.getvalue())
