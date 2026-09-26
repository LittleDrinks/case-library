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

from app.modules.documents import build_case_docx

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD_DRAWING_NS = (
    "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
)
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": WORD_NS}
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CASE_VERSION_URL = "https://case.test/#/cases/source-1?versionId=version-2"


def w(name: str) -> str:
    return f"{{{WORD_NS}}}{name}"


def login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    return response.json()


def transition_case(
    client: TestClient, case: dict, auth: dict, command: str, **extra
) -> dict:
    response = client.post(
        f"/api/cases/{case['id']}/lifecycle",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"command": command, "revision": case["revision"], **extra},
    )
    assert response.status_code == 200
    return response.json()


def _item(text: str) -> dict:
    return {
        "type": "listItem",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _continued_item(text: str) -> dict:
    return {
        "type": "listItem",
        "content": [
            _paragraph_node(text),
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": f"{text}续段一"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": f"{text}续段二"},
                ],
            },
        ],
    }


def _paragraph_node(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def _ordered_list_at_depth(label: str, depth: int, start: int) -> dict:
    result = {
        "type": "orderedList",
        "attrs": {"start": start},
        "content": [_item(label), _item(f"{label}-SECOND")],
    }
    for level in range(depth):
        result = {
            "type": "orderedList",
            "attrs": {"start": 1},
            "content": [
                {
                    "type": "listItem",
                    "content": [_paragraph_node(f"{label}-PARENT-{level + 1}"), result],
                }
            ],
        }
    return result


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
    "课前阅读材料；分组讨论；小组代表发表核心观点",
    "二、文本内容（2500字左右）",
    "（要求：主题鲜明，逻辑清晰，结构合理，文字流畅）",
    "三、附件",
    "推荐阅读书目和备课主要参考书（若有，5本左右）",
]


def rich_document() -> dict:
    return deepcopy(RICH_DOCUMENT)


def document_xml(data: bytes) -> Element:
    with ZipFile(BytesIO(data)) as package:
        return parse_xml(package.read("word/document.xml"))


def numbering_start_override(data: bytes, item_text: str) -> int | None:
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
    return int(start.get(w("val"))) if start is not None else None


def numbering_start(data: bytes, item_text: str) -> int:
    start = numbering_start_override(data, item_text)
    return 1 if start is None else start


def numbering_layout(data: bytes, item_text: str) -> tuple[str, int, int]:
    with ZipFile(BytesIO(data)) as package:
        document = parse_xml(package.read("word/document.xml"))
        numbering = parse_xml(package.read("word/numbering.xml"))
        styles = parse_xml(package.read("word/styles.xml"))
    item = paragraph(document, item_text)
    number_id = item.find("w:pPr/w:numPr/w:numId", NS)
    if number_id is None:
        style_id = item.find("w:pPr/w:pStyle", NS).get(w("val"))
        number_id = styles.find(
            f".//w:style[@w:styleId='{style_id}']/w:pPr/w:numPr/w:numId", NS
        )
    instance = next(
        entry
        for entry in numbering.findall("w:num", NS)
        if entry.get(w("numId")) == number_id.get(w("val"))
    )
    abstract_id = instance.find("w:abstractNumId", NS).get(w("val"))
    abstract = next(
        entry
        for entry in numbering.findall("w:abstractNum", NS)
        if entry.get(w("abstractNumId")) == abstract_id
    )
    indent = abstract.find("w:lvl/w:pPr/w:ind", NS)
    return (
        number_id.get(w("val")),
        int(indent.get(w("left"))),
        int(indent.get(w("hanging"))),
    )


def direct_list_format(data: bytes, item_text: str) -> tuple[str | None, ...]:
    item = paragraph(document_xml(data), item_text)
    indent = item.find("w:pPr/w:ind", NS)
    tab = item.find("w:pPr/w:tabs/w:tab", NS)
    return (
        indent.get(w("left")) if indent is not None else None,
        indent.get(w("hanging")) if indent is not None else None,
        tab.get(w("pos")) if tab is not None else None,
    )


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
    auth = login(client)
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "版式测试案例", "document": rich_document()},
    )
    case = response.json()
    export = client.get(f"/api/cases/{case['id']}/export.docx")
    return export, export.content


def create_default_case(client: TestClient) -> bytes:
    auth = login(client)
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "结构测试案例"},
    )
    case = response.json()
    return client.get(f"/api/cases/{case['id']}/export.docx").content


def export_document(client: TestClient, title: str, document: dict) -> bytes:
    auth = login(client)
    response = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": title, "document": document},
    )
    case_id = response.json()["id"]
    return client.get(f"/api/cases/{case_id}/export.docx").content


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


def test_public_docx_export_restarts_deep_ordered_lists(client: TestClient) -> None:
    user = login(client)
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": user["csrfToken"]},
        json={
            "title": "深层列表重启测试",
            "document": {
                "type": "doc",
                "content": [
                    _ordered_list_at_depth("ORDER-L1", 0, 3),
                    _ordered_list_at_depth("ORDER-L2", 1, 6),
                    _ordered_list_at_depth("ORDER-L3", 2, 1),
                    _ordered_list_at_depth("ORDER-L4", 3, 1),
                    _ordered_list_at_depth("ORDER-L5", 4, 1),
                    _ordered_list_at_depth("ORDER-L5-START5", 4, 5),
                ],
            },
        },
    )
    assert created.status_code == 200
    case = created.json()
    path = f"/api/cases/{case['id']}"
    current_export = client.get(path + "/export.docx")
    submitted = transition_case(client, case, user, "submit")
    admin = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    ).json()
    started = transition_case(client, submitted["case"], admin, "start")
    transition_case(
        client,
        started["case"],
        admin,
        "approve",
        submittedVersionId=submitted["version"]["id"],
    )
    client.cookies.clear()
    public_export = client.get(path + "/public/export.docx")
    assert current_export.status_code == public_export.status_code == 200

    roots = ["ORDER-L3", "ORDER-L4", "ORDER-L5"]
    lists = [
        ("ORDER-L1", 3),
        ("ORDER-L2", 6),
        ("ORDER-L3", 1),
        ("ORDER-L4", 1),
        ("ORDER-L5", 1),
        ("ORDER-L5-START5", 5),
    ]
    for response in (current_export, public_export):
        data = response.content
        assert [numbering_start_override(data, label) for label in roots] == [1, 1, 1]
        assert [numbering_start_override(data, label) for label, _ in lists] == [
            start for _, start in lists
        ]
        assert all(
            numbering_layout(data, label)[0]
            == numbering_layout(data, f"{label}-SECOND")[0]
            for label, _ in lists
        )
        assert len({numbering_layout(data, label)[0] for label in roots}) == 3


def test_docx_export_aligns_manual_lines_split_by_hard_break(
    client: TestClient,
) -> None:
    first = "（1）如何理解习近平文化思想中'两个结合'的实践路径？"
    second = "（2）校园文化活动中如何体现以人民为中心的发展思想？"
    ai_first, ai_second = "（1）AI 写入第一项", "（2）AI 写入第二项"
    document = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": first},
                    {"type": "hardBreak"},
                    {"type": "text", "text": second},
                ],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": ai_first + "\n" + ai_second}],
            },
        ],
    }
    auth = login(client)
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "软换行版式测试", "document": document},
    )
    case = created.json()
    material = client.post(
        f"/api/cases/{case['id']}/materials",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"materialId": "m-kcsz", "revision": case["revision"]},
    ).json()
    response = client.get(f"/api/cases/{case['id']}/export.docx")
    root = document_xml(response.content)

    assert created.status_code == 200
    assert response.status_code == 200
    exported = paragraph(root, first + second)
    assert len(exported.findall(".//w:br", NS)) == 1
    indent = exported.find("w:pPr/w:ind", NS)
    assert indent is not None
    assert indent.get(w("left")) == "420"
    assert indent.get(w("firstLine")) is None
    ai_exported = paragraph(root, ai_first + ai_second)
    assert len(ai_exported.findall(".//w:br", NS)) == 1
    ai_indent = ai_exported.find("w:pPr/w:ind", NS)
    assert ai_indent is not None
    assert ai_indent.get(w("left")) == "420"
    assert ai_indent.get(w("firstLine")) is None
    assert any(
        paragraph_text(item).startswith(f"〔1〕 {material['title']}．")
        for item in root.iter(w("p"))
    )


def test_docx_export_indents_nested_ordered_and_bullet_lists(
    client: TestClient,
) -> None:
    document = {
        "type": "doc",
        "content": [
            {
                "type": "orderedList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            _paragraph_node("顶层编号一"),
                            {
                                "type": "orderedList",
                                "content": [
                                    _item("嵌套编号一"),
                                    {
                                        "type": "listItem",
                                        "content": [
                                            _paragraph_node("嵌套编号二"),
                                            {
                                                "type": "orderedList",
                                                "content": [
                                                    {
                                                        "type": "listItem",
                                                        "content": [
                                                            _paragraph_node("三级编号"),
                                                            {
                                                                "type": "orderedList",
                                                                "content": [
                                                                    _continued_item(
                                                                        "四级编号"
                                                                    )
                                                                ],
                                                            },
                                                        ],
                                                    }
                                                ],
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    _item("顶层编号二"),
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            _paragraph_node("顶层项目一"),
                            {
                                "type": "bulletList",
                                "content": [
                                    _item("嵌套项目一"),
                                    {
                                        "type": "listItem",
                                        "content": [
                                            _paragraph_node("嵌套项目二"),
                                            {
                                                "type": "bulletList",
                                                "content": [
                                                    {
                                                        "type": "listItem",
                                                        "content": [
                                                            _paragraph_node("三级项目"),
                                                            {
                                                                "type": "bulletList",
                                                                "content": [
                                                                    _continued_item(
                                                                        "四级项目"
                                                                    )
                                                                ],
                                                            },
                                                        ],
                                                    }
                                                ],
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    _item("顶层项目二"),
                ],
            },
        ],
    }
    data = export_document(client, "嵌套列表测试", document)
    root = document_xml(data)

    assert paragraph_style(paragraph(root, "顶层编号一")) == "ListNumber"
    assert paragraph_style(paragraph(root, "顶层编号二")) == "ListNumber"
    assert paragraph_style(paragraph(root, "嵌套编号一")) == "ListNumber2"
    assert paragraph_style(paragraph(root, "嵌套编号二")) == "ListNumber2"
    assert paragraph_style(paragraph(root, "三级编号")) == "ListNumber3"
    assert paragraph_style(paragraph(root, "四级编号")) == "ListNumber3"
    assert paragraph_style(paragraph(root, "顶层项目一")) == "ListBullet"
    assert paragraph_style(paragraph(root, "顶层项目二")) == "ListBullet"
    assert paragraph_style(paragraph(root, "嵌套项目一")) == "ListBullet2"
    assert paragraph_style(paragraph(root, "嵌套项目二")) == "ListBullet2"
    assert paragraph_style(paragraph(root, "三级项目")) == "ListBullet3"
    assert paragraph_style(paragraph(root, "四级项目")) == "ListBullet3"

    ordered_one = numbering_layout(data, "顶层编号一")
    ordered_two = numbering_layout(data, "顶层编号二")
    nested_ordered = numbering_layout(data, "嵌套编号一")
    nested_ordered_two = numbering_layout(data, "嵌套编号二")
    third_ordered = numbering_layout(data, "三级编号")
    bullet = numbering_layout(data, "顶层项目一")
    nested_bullet = numbering_layout(data, "嵌套项目一")
    third_bullet = numbering_layout(data, "三级项目")
    assert ordered_one[0] == ordered_two[0]
    assert ordered_one[0] != nested_ordered[0]
    assert nested_ordered[0] == nested_ordered_two[0]
    assert ordered_one[1:] == (360, 360)
    assert nested_ordered[1:] == (720, 360)
    assert third_ordered[1:] == (1080, 360)
    assert direct_list_format(data, "三级编号") == (None, None, None)
    assert direct_list_format(data, "四级编号") == ("1440", "360", "1440")
    assert bullet[1:] == (360, 360)
    assert nested_bullet[1:] == (720, 360)
    assert third_bullet[1:] == (1080, 360)
    assert direct_list_format(data, "三级项目") == (None, None, None)
    assert direct_list_format(data, "四级项目") == ("1440", "360", "1440")
    for item_text in ("四级编号", "四级项目"):
        continuation = paragraph(root, f"{item_text}续段一{item_text}续段二")
        indent = continuation.find("w:pPr/w:ind", NS)
        assert indent is not None
        assert indent.get(w("left")) == "1440"
        assert indent.get(w("firstLine")) is None
        assert indent.get(w("hanging")) is None
        assert len(continuation.findall(".//w:br", NS)) == 1
    assert paragraph(root, "顶层编号一").find("w:pPr/w:ind", NS) is None
    assert paragraph(root, "嵌套编号一").find("w:pPr/w:ind", NS) is None


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


def citation(source_type: str, source_id: str) -> dict:
    return {
        "type": "citation",
        "attrs": {"sourceType": source_type, "sourceId": source_id},
    }


def cited_document() -> dict:
    first, second = citation("material", "image-1"), citation("case", "source-1")
    content = [
        {"type": "text", "text": "加粗依据", "marks": [{"type": "bold"}, first]},
        {"type": "text", "text": "斜体依据", "marks": [{"type": "italic"}, first]},
        {"type": "text", "text": "后续正文"},
        {"type": "text", "text": "再次引用", "marks": [second]},
    ]
    return {"type": "doc", "content": [{"type": "paragraph", "content": content}]}


def cited_entries() -> list[dict]:
    return [
        {
            "sourceType": "material",
            "id": "image-1",
            "number": 1,
            "title": "图片资料",
            "source": "图像库",
            "url": "https://case.test/api/materials/image-1/content",
        },
        {
            "sourceType": "case",
            "id": "source-1",
            "number": 2,
            "title": "引用案例",
            "source": "上海大学",
            "version": "v2",
            "url": CASE_VERSION_URL,
        },
        {
            "sourceType": "attachment",
            "id": "unused-1",
            "number": 3,
            "title": "未用附件",
            "url": "https://case.test/api/cases/c-1/attachments/unused-1/content?versionId=version-2",
        },
    ]


def docx_xml_and_links(data: bytes) -> tuple[Element, set[str]]:
    with ZipFile(BytesIO(data)) as package:
        root = parse_xml(package.read("word/document.xml"))
        relationships = parse_xml(package.read("word/_rels/document.xml.rels"))
        return root, {
            item.get("Target")
            for item in relationships
            if item.get("TargetMode") == "External"
        }


def test_docx_export_numbers_citations_and_links_all_retained_sources() -> None:
    case = {"title": "引用导出", "document": cited_document()}
    root, targets = docx_xml_and_links(build_case_docx(case, cited_entries()))
    texts = [paragraph_text(item) for item in root.iter(w("p"))]
    assert "加粗依据斜体依据〔1〕后续正文再次引用〔2〕" in texts
    references = [text for text in texts if text.startswith("〔")]
    assert references == [
        "〔1〕 图片资料．图像库．链接",
        "〔2〕 引用案例．上海大学．v2．链接",
        "〔3〕 未用附件．链接",
    ]
    assert targets == {
        "https://case.test/api/materials/image-1/content",
        CASE_VERSION_URL,
        "https://case.test/api/cases/c-1/attachments/unused-1/content?versionId=version-2",
    }


def test_docx_material_source_link_opens_platform_page_and_keeps_download_access(
    client: TestClient,
) -> None:
    material_id = "m-docx-source"
    blob_id = "docx-source-blob"
    original = b"authorized source bytes"
    client.app.state.database.materials.insert_one(
        {
            "id": material_id,
            "title": "导出来源素材",
            "summary": "受限摘要标记",
            "excerpt": "受限正文标记",
            "source": "受限来源信息",
            "sourceUrl": "https://source.example/material",
            "status": "active",
            "accessLevel": "private",
            "createdBy": "u-user-demo",
            "blobId": blob_id,
            "filename": "source.txt",
            "mediaType": "text/plain",
            "size": len(original),
        }
    )
    client.app.state.blob_store.put(
        blob_id, BytesIO(original), len(original), "text/plain"
    )

    denied_detail = client.get(f"/api/materials/{material_id}")
    denied_download = client.get(f"/api/materials/{material_id}/content")
    assert denied_detail.status_code == denied_download.status_code == 404
    assert not any(
        value in denied_detail.text
        for value in ("导出来源素材", "受限摘要标记", "受限正文标记", "受限来源信息")
    )

    auth = login(client)
    created = client.post(
        "/api/cases",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"title": "来源链接验收"},
    )
    assert created.status_code == 200
    case = created.json()
    mounted = client.post(
        f"/api/cases/{case['id']}/materials",
        headers={"X-CSRF-Token": auth["csrfToken"]},
        json={"materialId": material_id, "revision": case["revision"]},
    )
    assert mounted.status_code == 201

    export = client.get(f"/api/cases/{case['id']}/export.docx")
    assert export.status_code == 200
    _, targets = docx_xml_and_links(export.content)
    assert f"http://testserver/#/materials/{material_id}" in targets
    assert f"http://testserver/api/materials/{material_id}/content" not in targets

    detail = client.get(f"/api/materials/{material_id}")
    download = client.get(f"/api/materials/{material_id}/content")
    assert detail.status_code == 200
    assert download.status_code == 200
    assert download.content == original


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
