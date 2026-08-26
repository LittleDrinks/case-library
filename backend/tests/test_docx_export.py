from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from uuid import UUID
from xml.etree.ElementTree import Element
from xml.etree.ElementTree import fromstring as parse_xml
from zipfile import ZipFile

from docx import Document as open_docx
from fastapi.testclient import TestClient
from httpx import Response

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_DRAWING_NS = (
    "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
)
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": WORD_NS}
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def w(name: str) -> str:
    return f"{{{WORD_NS}}}{name}"


def login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    return response.json()


def _item(text: str) -> dict:
    return {
        "type": "listItem",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _paragraph_node(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


RICH_DOCUMENT = {
    "type": "doc",
    "content": [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "一、教学说明（800字左右）"}],
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "重点", "marks": [{"type": "bold"}]},
                {"type": "text", "text": "内容", "marks": [{"type": "italic"}]},
            ],
        },
        {"type": "bulletList", "content": [_item("课前阅读材料"), _item("分组讨论")]},
        {"type": "orderedList", "content": [_item("第一题"), _item("第二题")]},
    ],
}

REQUIRED_STRUCTURE = [
    "一、教学说明（800字左右）",
    "（一）教学目的",
    "（二）阅读思考题（2～3个）",
    "（三）教学安排",
    "（四）注意事项",
    "二、文本内容（2500字左右）",
    "三、附件",
]


def rich_document() -> dict:
    return deepcopy(RICH_DOCUMENT)


def document_xml(data: bytes) -> Element:
    with ZipFile(BytesIO(data)) as package:
        return parse_xml(package.read("word/document.xml"))


def numbering_start(data: bytes, item_text: str) -> int:
    with ZipFile(BytesIO(data)) as package:
        document = parse_xml(package.read("word/document.xml"))
        numbering = parse_xml(package.read("word/numbering.xml"))
    num_id = paragraph(document, item_text).find("w:pPr/w:numPr/w:numId", NS)
    assert num_id is not None
    instance = next(
        item
        for item in numbering.findall("w:num", NS)
        if item.get(w("numId")) == num_id.get(w("val"))
    )
    start = instance.find("w:lvlOverride/w:startOverride", NS)
    return int(start.get(w("val"))) if start is not None else 1


def paragraph_text(paragraph: Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(w("t")))


def paragraph(root: Element, text: str) -> Element:
    return next(item for item in root.iter(w("p")) if paragraph_text(item) == text)


def run(paragraph_node: Element, text: str) -> Element:
    return next(
        item for item in paragraph_node.iter(w("r")) if paragraph_text(item) == text
    )


def east_asia_font(node: Element) -> str | None:
    fonts = node.find(".//w:rFonts", NS)
    return fonts.get(w("eastAsia")) if fonts is not None else None


def font_size(node: Element) -> str | None:
    size = node.find(".//w:sz", NS)
    return size.get(w("val")) if size is not None else None


def paragraph_style(node: Element) -> str | None:
    style = node.find("w:pPr/w:pStyle", NS)
    return style.get(w("val")) if style is not None else None


def package_relationships(package: ZipFile) -> list[Element]:
    names = (name for name in package.namelist() if name.endswith(".rels"))
    return [item for name in names for item in parse_xml(package.read(name))]


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def deobfuscate_font(data: bytes, font_key: str) -> bytes:
    key = bytes.fromhex(font_key.strip("{}").replace("-", ""))[::-1]
    decoded = bytearray(data)
    for index in range(32):
        decoded[index] ^= key[index % 16]
    return bytes(decoded)


def ttf_table(data: bytes, name: bytes) -> bytes:
    table_count = int.from_bytes(data[4:6], "big")
    for position in range(12, 12 + table_count * 16, 16):
        record = data[position : position + 16]
        if record[:4] == name:
            offset = int.from_bytes(record[8:12], "big")
            length = int.from_bytes(record[12:16], "big")
            return data[offset : offset + length]
    raise AssertionError(f"TTF table not found: {name!r}")


def create_rich_case(client: TestClient) -> tuple[Response, bytes]:
    case = create_case(client, login(client), "版式测试案例", rich_document())
    export = client.get(f"/api/cases/{case['id']}/export.docx")
    return export, export.content


def create_default_case(client: TestClient) -> bytes:
    case = create_case(
        client,
        login(client),
        "结构测试案例",
        template_id="tpl-teaching-standard-v1",
    )
    return client.get(f"/api/cases/{case['id']}/export.docx").content


def export_document(client: TestClient, title: str, document: dict) -> bytes:
    case = create_case(client, login(client), title, document)
    return client.get(f"/api/cases/{case['id']}/export.docx").content


def create_case(
    client: TestClient,
    auth: dict,
    title: str,
    document: dict | None = None,
    template_id: str = "tpl-general-v1",
) -> dict:
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=_selection(template_id),
    )
    assert response.status_code == 200
    return _save_case(client, auth, response.json(), title, document)


def _save_case(
    client: TestClient, auth: dict, case: dict, title: str, document: dict | None
) -> dict:
    changes = {"title": title, "revision": case["revision"]}
    if document is not None:
        changes["document"] = document
    saved = client.patch(
        f"/api/cases/{case['id']}",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json=changes,
    )
    assert saved.status_code == 200
    return saved.json()


def _selection(template_id: str) -> dict:
    return {
        "stageId": "ug",
        "typeId": "ct-figure",
        "templateId": template_id,
    }


def assert_typography(root: Element) -> None:
    title = paragraph(root, "版式测试案例")
    heading = paragraph(root, "一、教学说明（800字左右）")
    body = paragraph(root, "重点内容")
    assert (east_asia_font(title), font_size(title)) == ("方正小标宋简体", "36")
    assert (east_asia_font(heading), font_size(heading)) == ("黑体", "32")
    assert (east_asia_font(body), font_size(body)) == ("宋体", "24")


def assert_content_formatting(root: Element) -> None:
    body = paragraph(root, "重点内容")
    assert run(body, "重点").find(".//w:b", NS) is not None
    assert run(body, "内容").find(".//w:i", NS) is not None
    assert paragraph_style(paragraph(root, "课前阅读材料")) == "ListBullet"
    assert paragraph_style(paragraph(root, "第一题")) == "ListNumber"


def assert_page_layout(root: Element) -> None:
    page = root.find(".//w:sectPr", NS)
    assert page.find("w:pgSz", NS).attrib == {w("w"): "11906", w("h"): "16838"}
    assert page.find("w:pgMar", NS).get(w("left")) == "1701"
    body = paragraph(root, "重点内容")
    spacing = body.find("w:pPr/w:spacing", NS)
    assert (spacing.get(w("line")), spacing.get(w("lineRule"))) == ("440", "exact")
    assert spacing.get(w("after")) == "80"
    assert body.find("w:pPr/w:ind", NS).get(w("firstLine")) == "420"


def embedded_font(package: ZipFile) -> tuple[bytes, str]:
    fonts = parse_xml(package.read("word/fontTable.xml"))
    font = next(item for item in fonts if item.get(w("name")) == "方正小标宋简体")
    embedded = font.find("w:embedRegular", NS)
    font_key = embedded.get(w("fontKey"))
    relation_id = embedded.get(f"{{{OFFICE_REL_NS}}}id")
    relationships = parse_xml(package.read("word/_rels/fontTable.xml.rels"))
    relationship = next(item for item in relationships if item.get("Id") == relation_id)
    assert relationship.get("Type", "").endswith("/font")
    return deobfuscate_font(
        package.read(f"word/{relationship.get('Target')}"), font_key
    ), font_key


def has_font_content_type(package: ZipFile) -> bool:
    content_types = parse_xml(package.read("[Content_Types].xml"))
    return any(
        item.get("Extension") == "odttf"
        and item.get("ContentType")
        == "application/vnd.openxmlformats-officedocument.obfuscatedFont"
        for item in content_types.findall(f"{{{CONTENT_TYPES_NS}}}Default")
    )


def assert_embedded_logo(package: ZipFile) -> None:
    relationships = parse_xml(package.read("word/_rels/document.xml.rels"))
    document = parse_xml(package.read("word/document.xml"))
    image_relationships = [
        item for item in relationships if item.get("Type", "").endswith("/image")
    ]
    assert len(image_relationships) == 1
    relationship = image_relationships[0]
    image = package.read(f"word/{relationship.get('Target')}")
    assert png_size(image) == (1130, 365)
    blip = document.find(f".//{{{DRAWING_NS}}}blip")
    assert blip.get(f"{{{OFFICE_REL_NS}}}embed") == relationship.get("Id")
    doc_properties = document.find(f".//{{{WORD_DRAWING_NS}}}docPr")
    assert doc_properties.get("descr") == "上海大学校徽"
    assert not any(
        item.get("TargetMode") == "External" for item in package_relationships(package)
    )


def test_docx_export_uses_case_read_permissions(client: TestClient) -> None:
    denied = client.get("/api/cases/c-draft-1/export.docx")
    assert denied.status_code == 404

    login(client)
    response = client.get("/api/cases/c-draft-1/export.docx")

    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_TYPE
    assert response.headers["content-disposition"] == (
        'attachment; filename="case-c-draft-1.docx"'
    )
    assert response.content.startswith(b"PK")


def test_docx_export_has_fixed_layout_and_prosemirror_formatting(
    client: TestClient,
) -> None:
    response, data = create_rich_case(client)
    root = document_xml(data)

    assert response.status_code == 200
    assert_typography(root)
    assert_content_formatting(root)
    assert_page_layout(root)


def test_docx_export_preserves_ordered_list_start(client: TestClient) -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "orderedList",
                "attrs": {"start": 5},
                "content": [_item("第五题"), _item("第六题")],
            }
        ],
    }
    data = export_document(client, "编号起始值测试", document)

    assert numbering_start(data, "第五题") == 5


def test_docx_export_preserves_blockquote_paragraphs(client: TestClient) -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "blockquote",
                "content": [
                    _paragraph_node("引用第一段"),
                    _paragraph_node("引用第二段"),
                ],
            }
        ],
    }
    root = document_xml(export_document(client, "引用测试", document))
    quotes = [item for item in root.iter(w("p")) if paragraph_style(item) == "Quote"]

    assert [paragraph_text(item) for item in quotes] == ["引用第一段", "引用第二段"]


def test_docx_export_preserves_the_required_case_structure(client: TestClient) -> None:
    root = document_xml(create_default_case(client))
    texts = [paragraph_text(item) for item in root.iter(w("p"))]
    positions = [texts.index(text) for text in REQUIRED_STRUCTURE]
    assert positions == sorted(positions)


def test_docx_export_embeds_the_cropped_university_logo(client: TestClient) -> None:
    _, data = create_rich_case(client)
    with ZipFile(BytesIO(data)) as package:
        assert_embedded_logo(package)
    reopened = open_docx(BytesIO(data))
    assert len(reopened.inline_shapes) == 1
    assert reopened.core_properties.title == "版式测试案例"


def test_docx_export_embeds_the_editable_title_font(client: TestClient) -> None:
    _, data = create_rich_case(client)
    with ZipFile(BytesIO(data)) as package:
        decoded, font_key = embedded_font(package)
        UUID(font_key.strip("{}"))
        assert sha256(decoded).hexdigest() == (
            "2322dbfb4fe3b51e5f530c0ee668a7d83df20c0fd8b1aa113a0a9e7ee45d45f3"
        )
        assert int.from_bytes(ttf_table(decoded, b"OS/2")[8:10], "big") == 0x0008
        settings = parse_xml(package.read("word/settings.xml"))
        assert settings.find("w:embedTrueTypeFonts", NS) is not None
        assert has_font_content_type(package)
