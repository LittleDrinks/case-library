"""来源读取领域服务：按当前身份读取资料区与检索命中的真实内容。

资料区条目按统一来源 API 的稳定条目 id 解析：案例来源条目解析到真实
来源案例与挂载时固定的已批准版本，不按标题或首行匹配推断。每次读取
都重新校验权限与下线状态；无权限、空内容、暂不可用与错误以显式状态
返回，不生成虚假证据。可选 case_version_id 把读取范围固定到冻结版本，
供只读工作台集成；权限校验不因固定版本而放宽。
"""

from __future__ import annotations

import io
from pymongo.database import Database

from app.modules.agent.case_area import area_rows
from app.modules.agent.models import SourceRef
from app.modules.agent.prosemirror import paragraphs as document_paragraphs
from app.modules.attachments.text import extract_search_text
from app.modules.cases.published import version_readable
from app.modules.cases.sources import source_case_content_available
from app.modules.materials.service import can_read_material, campus_verified

MAX_SOURCE_CHARACTERS = 6000
NO_ACCESS, UNAVAILABLE = "no_access", "unavailable"
EMPTY, ERROR, OK = "empty", "error", "ok"


class _BlobFile:
    """BlobStore 字节流的 upload 视图，复用既有文本抽取。"""

    def __init__(self, data: bytes, media_type: str, filename: str):
        self.file = io.BytesIO(data)
        self.content_type = media_type
        self.filename = filename


def read_source(database: Database, store, user: dict | None, case_id: str,
                source_type: str, source_id: str,
                case_version_id: str | None = None) -> dict:
    """读取一个来源：返回 ok+内容 或 no_access/empty/unavailable/error。"""
    readers = {
        "attachment": lambda: _read_attachment(
            database, store, user, case_id, source_id, case_version_id,
        ),
        "material": lambda: _read_material(
            database, store, user, case_id, source_id, case_version_id,
        ),
        "case": lambda: _read_case(database, user, case_id, source_id, case_version_id),
        "knowledge": lambda: _read_knowledge(database, source_id),
    }
    reader = readers.get(source_type)
    if reader is None:
        return {"status": ERROR, "detail": "来源类型不支持"}
    return reader()


def _failed(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def _succeeded(ref: SourceRef, text: str) -> dict:
    content, truncated = text[:MAX_SOURCE_CHARACTERS], len(text) > MAX_SOURCE_CHARACTERS
    if not content.strip():
        return {"status": EMPTY, "source": ref.model_dump(by_alias=True), "detail": "来源无可读取文字"}
    return {
        "status": OK, "source": ref.model_dump(by_alias=True), "content": content,
        "truncated": truncated,
    }


def _area_row(database: Database, case_id: str, kind: str, source_id: str,
              version_id: str | None) -> dict | None:
    rows = area_rows(database, case_id, version_id)[kind]
    keys = ("materialId", "id") if kind == "material" else ("id",)
    return next(
        (row for row in rows if any(row.get(key) == source_id for key in keys)), None
    )


def _read_attachment(database: Database, store, user, case_id: str, source_id: str,
                     version_id: str | None) -> dict:
    row = _area_row(database, case_id, "attachment", source_id, version_id)
    if not row:
        return _failed(UNAVAILABLE, "附件已删除或不在资料区")
    if not _attachment_readable(database, case_id, row, user):
        return _failed(NO_ACCESS, "当前身份无权读取该附件内容")
    text = row.get("searchText") or _blob_text(store, row)
    ref = SourceRef(
        kind="attachment", id=row["id"], title=row.get("name") or "",
        locator=f"attachment:{case_id}/{row['id']}",
    )
    return _succeeded(ref, text)


def _attachment_readable(database: Database, case_id: str, row: dict, user) -> bool:
    case = database.cases.find_one({"id": case_id}) or {}
    if _internal(case, user):
        return True
    level = row.get("accessLevel", "public")
    if level == "public":
        return True
    return level == "campus" and campus_verified(user)


def _read_material(database: Database, store, user, case_id: str, source_id: str,
                   version_id: str | None) -> dict:
    if not _area_row(database, case_id, "material", source_id, version_id):
        return _failed(UNAVAILABLE, "素材不在当前案例资料区")
    row = database.materials.find_one({"id": source_id})
    if not row or row.get("status") != "active":
        return _failed(UNAVAILABLE, "素材不存在或已下线")
    if not can_read_material(row, user):
        return _failed(NO_ACCESS, "当前身份无权读取该素材内容")
    text = _blob_text(store, row)
    ref = SourceRef(
        kind="material", id=row["id"], title=row.get("title") or "",
        locator=f"material:{row['id']}",
    )
    return _succeeded(ref, text)


def _blob_text(store, row: dict) -> str:
    if not row.get("blobId"):
        return ""
    data = b"".join(store.open(row["blobId"]))
    upload = _BlobFile(data, row.get("mediaType") or "", row.get("filename") or "")
    return extract_search_text(upload)


def _read_case(database: Database, user, case_id: str, source_id: str,
               version_id: str | None) -> dict:
    pinned = _area_row(database, case_id, "case", source_id, version_id)
    if pinned:
        return _read_pinned_case(database, user, pinned)
    return _read_case_hit(database, user, source_id)


def _read_pinned_case(database: Database, user, pinned: dict) -> dict:
    source_id = pinned["sourceCaseId"]
    case = database.cases.find_one({"id": source_id})
    if not case:
        return _failed(UNAVAILABLE, "来源案例已删除")
    if not source_case_content_available(database, source_id, user):
        return _failed(NO_ACCESS, "来源案例内容当前不可读")
    version = database.case_versions.find_one({"id": pinned["versionId"]})
    if not version:
        return _failed(UNAVAILABLE, "来源版本已不可用")
    return _case_result(database, case, version, _internal(case, user))


def _read_case_hit(database: Database, user, source_id: str) -> dict:
    case = database.cases.find_one({"id": source_id})
    if not case:
        return _failed(ERROR, "来源不在资料区，也不在本次检索结果中")
    internal = _internal(case, user)
    if not internal and case.get("publicationStatus") != "public":
        return _failed(NO_ACCESS, "案例未公开，当前身份不可读")
    version_id = case.get("publishedVersionId")
    version = database.case_versions.find_one({"id": version_id, "caseId": source_id})
    if not version_id or not version:
        return _failed(UNAVAILABLE, "案例暂无已发布版本")
    return _case_result(database, case, version, internal)


def _internal(case: dict, user) -> bool:
    return bool(user and (user["role"] == "admin" or case.get("ownerId") == user["id"]))


def _case_result(database: Database, case: dict, version: dict, internal: bool) -> dict:
    if not version_readable(database, case, version["id"], version, internal):
        return _failed(NO_ACCESS, "该版本当前不可读")
    document = version.get("document") or {}
    text = "\n".join(row["quote"] for row in document_paragraphs(document))
    ref = SourceRef(
        kind="case", id=case["id"], title=version.get("title") or "",
        version=f"v{version['number']}", version_id=version["id"],
        locator=f"case:{case['id']}@{version['id']}",
    )
    return _succeeded(ref, text)


def _read_knowledge(database: Database, source_id: str) -> dict:
    section = database.knowledge_sections.find_one({"id": source_id})
    if not section:
        return _failed(UNAVAILABLE, "教材章节不存在")
    source = database.knowledge_sources.find_one(
        {"id": section.get("sourceId"), "status": "active"}
    )
    if not source:
        return _failed(UNAVAILABLE, "教材已下线")
    title = " · ".join(
        part for part in (section.get("chapter"), section.get("title")) if part
    )
    ref = SourceRef(
        kind="knowledge", id=source_id, title=title,
        version=source.get("edition"), locator=f"knowledge:{source_id}",
    )
    return _succeeded(ref, section.get("content") or "")
