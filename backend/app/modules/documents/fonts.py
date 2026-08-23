from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
FONT_REL = f"{R_NS}/font"
FONT_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.obfuscatedFont"
FONT_NAME = "方正小标宋简体"
FONT_PART = "word/fonts/fzxbsjw.odttf"
FONT_TARGET = "fonts/fzxbsjw.odttf"
FONT_PATH = Path(__file__).with_name("assets") / "FZXBSJW.TTF"


def _qname(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def _font_key(font: bytes) -> UUID:
    return UUID(bytes=sha256(font).digest()[:16])


def _obfuscate(font: bytes, font_key: UUID) -> bytes:
    key = font_key.bytes[::-1]
    obfuscated = bytearray(font)
    for index in range(32):
        obfuscated[index] ^= key[index % 16]
    return bytes(obfuscated)


def _add_content_type(data: bytes) -> bytes:
    root = etree.fromstring(data)
    element = etree.Element(_qname(CT_NS, "Default"))
    element.set("Extension", "odttf")
    element.set("ContentType", FONT_CONTENT_TYPE)
    defaults = root.findall(_qname(CT_NS, "Default"))
    root.insert(len(defaults), element)
    return _serialize(root)


def _add_font_setting(data: bytes) -> bytes:
    root = etree.fromstring(data)
    anchor = root.find(_qname(W_NS, "characterSpacingControl"))
    root.insert(root.index(anchor), etree.Element(_qname(W_NS, "embedTrueTypeFonts")))
    return _serialize(root)


def _add_font_record(data: bytes, font_key: UUID) -> bytes:
    root = etree.fromstring(data)
    font = etree.SubElement(root, _qname(W_NS, "font"))
    font.set(_qname(W_NS, "name"), FONT_NAME)
    embedded = etree.SubElement(font, _qname(W_NS, "embedRegular"))
    embedded.set(_qname(R_NS, "id"), "rId1")
    embedded.set(_qname(W_NS, "fontKey"), f"{{{str(font_key).upper()}}}")
    return _serialize(root)


def _font_relationships() -> bytes:
    root = etree.Element(_qname(REL_NS, "Relationships"), nsmap={None: REL_NS})
    relationship = etree.SubElement(root, _qname(REL_NS, "Relationship"))
    relationship.set("Id", "rId1")
    relationship.set("Type", FONT_REL)
    relationship.set("Target", FONT_TARGET)
    return _serialize(root)


def _read_package(data: bytes) -> tuple[list[ZipInfo], dict[str, bytes]]:
    with ZipFile(BytesIO(data)) as package:
        infos = package.infolist()
        return infos, {info.filename: package.read(info) for info in infos}


def _write_package(infos: list[ZipInfo], parts: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as package:
        for info in infos:
            package.writestr(info, parts.pop(info.filename))
        for name, data in parts.items():
            package.writestr(name, data)
    return buffer.getvalue()


def embed_title_font(data: bytes) -> bytes:
    font = FONT_PATH.read_bytes()
    font_key = _font_key(font)
    infos, parts = _read_package(data)
    parts["[Content_Types].xml"] = _add_content_type(parts["[Content_Types].xml"])
    parts["word/settings.xml"] = _add_font_setting(parts["word/settings.xml"])
    parts["word/fontTable.xml"] = _add_font_record(
        parts["word/fontTable.xml"], font_key
    )
    parts["word/_rels/fontTable.xml.rels"] = _font_relationships()
    parts[FONT_PART] = _obfuscate(font, font_key)
    return _write_package(infos, parts)
