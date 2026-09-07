"""Read one current source with explicit access and availability states."""

from __future__ import annotations

import io

from app.modules.attachments.service import AttachmentError, download_attachment
from app.modules.agent.case_area import area_rows
from app.modules.cases.sources import ordered_entries
from app.modules.agent.models import SourceRef
from app.modules.agent.prosemirror import paragraphs
from app.modules.attachments.text import extract_search_text
from app.modules.case_sources.service import source_case_content_available
from app.modules.materials.service import can_read_material

MAX_SOURCE_CHARACTERS = 6000
NO_ACCESS, UNAVAILABLE = "no_access", "unavailable"
EMPTY, ERROR, OK = "empty", "error", "ok"


class _BlobFile:
    def __init__(self, data: bytes, media_type: str, filename: str):
        self.file = io.BytesIO(data)
        self.content_type = media_type
        self.filename = filename


def read_source(database, store, user: dict | None, case_id: str,
                source_type: str, source_id: str, version_id: str | None = None) -> dict:
    readers = {
        "attachment": lambda: _read_attachment(
            database, store, user, case_id, source_id, version_id
        ),
        "material": lambda: _read_material(database, store, user, source_id),
        "case": lambda: _read_case(database, user, case_id, source_id, version_id),
        "knowledge": lambda: _read_knowledge(database, source_id),
    }
    try:
        return readers.get(source_type, lambda: _failed(ERROR, "来源类型不支持"))()
    except Exception:
        return _failed(ERROR, "来源读取失败")


def _failed(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def _succeeded(ref: SourceRef, text: str) -> dict:
    view = ref.model_dump(by_alias=True, exclude_none=True)
    if not text.strip():
        return {"status": EMPTY, "source": view, "usedSourceRef": view, "detail": "来源无可读取文字"}
    return {"status": OK, "source": view, "usedSourceRef": view,
            "content": text[:MAX_SOURCE_CHARACTERS], "truncated": len(text) > MAX_SOURCE_CHARACTERS}


def _area_row(database, case_id: str, kind: str, source_id: str,
              version_id: str | None = None) -> dict | None:
    rows = area_rows(database, case_id, version_id)[kind]
    keys = ("materialId", "id") if kind == "material" else ("id",)
    return next((row for row in rows if any(row.get(key) == source_id for key in keys)), None)


def _read_attachment(database, store, user, case_id: str, source_id: str,
                     version_id: str | None = None) -> dict:
    row = _area_row(database, case_id, "attachment", source_id, version_id)
    if not row:
        return _failed(UNAVAILABLE, "附件已删除或不在资料区")
    try:
        attachment, content = download_attachment(
            database, store, case_id, source_id, user, version_id
        )
    except AttachmentError as error:
        status = NO_ACCESS if error.status_code == 403 else UNAVAILABLE
        return _failed(status, error.detail)
    text = attachment.get("searchText") or _stream_text(content, attachment)
    ref = SourceRef(kind="attachment", id=row["id"], title=row.get("name") or "",
                    location=f"attachment:{case_id}/{row['id']}")
    return _succeeded(ref, text)


def _read_material(database, store, user: dict | None, source_id: str) -> dict:
    row = database.materials.find_one({"id": source_id, "status": "active"})
    if not row:
        return _failed(UNAVAILABLE, "素材不存在或已下线")
    if not can_read_material(row, user):
        return _failed(NO_ACCESS, "当前身份无权读取该素材内容")
    ref = SourceRef(kind="material", id=source_id, title=row.get("title") or "",
                    location=f"material:{source_id}")
    return _succeeded(ref, _blob_text(store, row))


def _blob_text(store, row: dict) -> str:
    if not store or not row.get("blobId"):
        return ""
    data = b"".join(store.open(row["blobId"]))
    upload = _BlobFile(data, row.get("mediaType") or "", row.get("filename") or "")
    return extract_search_text(upload)


def _stream_text(content, row: dict) -> str:
    data = b"".join(content)
    return extract_search_text(_BlobFile(data, row.get("mediaType") or "", row.get("name") or ""))


def _read_case(database, user: dict | None, case_id: str, source_id: str,
               version_id: str | None = None) -> dict:
    mounted = _area_row(database, case_id, "case", source_id, version_id)
    if mounted:
        return _read_pinned_case(database, user, mounted)
    return _read_published_case(database, source_id)


def _read_pinned_case(database, user: dict | None, row: dict) -> dict:
    case = database.cases.find_one({"id": row.get("sourceCaseId")})
    version = database.case_versions.find_one({"id": row.get("versionId"), "caseId": row.get("sourceCaseId")})
    if not case:
        return _failed(UNAVAILABLE, "来源案例已删除")
    if not version:
        return _failed(UNAVAILABLE, "来源版本已不可用")
    if not source_case_content_available(
        database, row.get("sourceCaseId"), user, version["id"], False
    ):
        return _failed(NO_ACCESS, "来源案例内容当前不可读")
    return _case_result(case, version, row["id"])


def _read_published_case(database, source_id: str) -> dict:
    case = database.cases.find_one({"id": source_id})
    version_id = (case or {}).get("publishedVersionId")
    version = database.case_versions.find_one({"id": version_id, "caseId": source_id}) if version_id else None
    if not case or not version:
        return _failed(UNAVAILABLE, "来源案例暂无已发布版本")
    if not source_case_content_available(database, source_id, None, version_id, False):
        return _failed(NO_ACCESS, "来源案例内容当前不可读")
    return _case_result(case, version)


def _case_result(case: dict, version: dict, source_id: str | None = None) -> dict:
    text = "\n".join(row["quote"] for row in paragraphs(version.get("document") or {}))
    ref = SourceRef(kind="case", id=source_id or case["id"], title=version.get("title") or "",
                    version=f"v{version['number']}", version_id=version["id"],
                    source_case_id=case["id"],
                    location=f"case:{case['id']}@{version['id']}")
    return _succeeded(ref, text)


def _read_knowledge(database, source_id: str) -> dict:
    section = database.knowledge_sections.find_one({"id": source_id})
    source = database.knowledge_sources.find_one({"id": (section or {}).get("sourceId"), "status": "active"})
    if not section or not source:
        return _failed(UNAVAILABLE, "教材章节不存在或已下线")
    title = " · ".join(part for part in (section.get("chapter"), section.get("title")) if part)
    ref = SourceRef(kind="knowledge", id=source_id, title=title,
                    version=source.get("edition"), location=f"knowledge:{source_id}")
    return _succeeded(ref, section.get("content") or "")


def source_readable(database, user: dict | None, case_id: str, ref: SourceRef) -> bool:
    if ref.kind == "attachment":
        return _area_entry_available(database, user, case_id, ref)
    if ref.kind == "case" and ref.version_id:
        source_case_id = ref.source_case_id or _location_case_id(ref.location)
        if source_case_id:
            return source_case_content_available(
                database, source_case_id, user, ref.version_id, False
            )
    result = read_source(database, None, user, case_id, ref.kind, ref.id)
    return result.get("status") not in {NO_ACCESS, UNAVAILABLE, ERROR}


def _location_case_id(location: str | None) -> str | None:
    if not location or not location.startswith("case:"):
        return None
    value = location[5:].split("@", 1)[0]
    return value or None


def _area_entry_available(database, user: dict | None, case_id: str, ref: SourceRef) -> bool:
    case = database.cases.find_one({"id": case_id}) or {"id": case_id}
    entry = next((item for item in ordered_entries(database, case, user, "")
                  if item["sourceType"] == ref.kind and item["id"] == ref.id), None)
    return bool(entry and entry.get("contentAvailable"))


def revalidate_sources(database, user: dict | None, case_id: str,
                       refs: list[SourceRef]) -> bool:
    return all(source_readable(database, user, case_id, ref) for ref in refs)
