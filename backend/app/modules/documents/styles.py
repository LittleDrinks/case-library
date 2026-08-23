from __future__ import annotations

from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.dml.color import RGBColor
from docx.shared import Mm, Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run

TITLE_FONT = "方正小标宋简体"
HEADING_FONT = "黑体"
BODY_FONT = "宋体"
TITLE_SIZE = 18
HEADING_SIZE = 16
BODY_SIZE = 12


def set_run_font(run: Run, font_name: str, size: int) -> None:
    run.font.name = font_name
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    properties = run._element.get_or_add_rPr()
    properties.get_or_add_rFonts().set(qn("w:eastAsia"), font_name)


def _set_style_font(
    document: DocxDocument, style_name: str, font: str, size: int
) -> None:
    style = document.styles[style_name]
    style.font.name = font
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor(0, 0, 0)
    if style.type == WD_STYLE_TYPE.PARAGRAPH:
        properties = style.element.get_or_add_rPr()
        properties.get_or_add_rFonts().set(qn("w:eastAsia"), font)


def configure_document(document: DocxDocument) -> None:
    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin = section.bottom_margin = Mm(25.4)
    section.left_margin = section.right_margin = Mm(30)
    _set_style_font(document, "Title", TITLE_FONT, TITLE_SIZE)
    _set_style_font(document, "Normal", BODY_FONT, BODY_SIZE)
    for name in ("Heading 1", "Heading 2", "Heading 3"):
        _set_style_font(document, name, HEADING_FONT, HEADING_SIZE)
    for name in ("List Bullet", "List Number", "Quote"):
        _set_style_font(document, name, BODY_FONT, BODY_SIZE)


def format_title(paragraph: Paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(18)
    paragraph.paragraph_format.line_spacing = Pt(32)


def format_heading(paragraph: Paragraph) -> None:
    paragraph.paragraph_format.space_before = Pt(12)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = Pt(28)
    paragraph.paragraph_format.keep_with_next = True


def format_body(paragraph: Paragraph, *, indented: bool = True) -> None:
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = Pt(22)
    if indented:
        paragraph.paragraph_format.first_line_indent = Pt(21)
