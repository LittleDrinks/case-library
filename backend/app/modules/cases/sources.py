"""资料区统一条目：排序、编号、链接与引用完整性检查。"""
from __future__ import annotations

from pymongo.database import Database

from app.modules.cases.document_schema import citation_refs
from app.modules.cases.service import CaseError
from app.modules.materials.service import campus_verified, can_read_material

SOURCE_COLLECTIONS = {
    "attachment": ("attachments", "id"),
    "material": ("case_materials", "materialId"),
    "case": ("case_sources", "id"),
}


def is_internal(record: dict, user: dict | None) -> bool:
    return bool(user and (user["role"] == "admin" or record.get("ownerId") == user["id"]))


def source_case_content_available(
    database: Database, source_case_id: str, user: dict | None
) -> bool:
    source = database.cases.find_one({"id": source_case_id})
    if not source:
        return False
    if source.get("publicationStatus") == "public":
        return True
    return bool(user and (user["role"] == "admin" or source["ownerId"] == user["id"]))


def require_uncited(
    database: Database, case_id: str, source_type: str, source_id: str, session
) -> None:
    case = database.cases.find_one({"id": case_id}, session=session)
    refs = citation_refs((case or {}).get("document", {}))
    if any(
        ref["sourceType"] == source_type and ref["sourceId"] == source_id
        for ref in refs
    ):
        raise CaseError(409, "来源仍被正文引用，请先删除或替换引用标记")


def citations_resolve(database: Database, case_id: str, document: dict, session) -> None:
    for ref in citation_refs(document):
        collection, field = SOURCE_COLLECTIONS[ref["sourceType"]]
        query = {"caseId": case_id, field: ref["sourceId"]}
        found = database[collection].count_documents(
            query, limit=1, session=session
        )
        if not found:
            raise CaseError(422, "正文引用的来源不在资料区")


def _source_rows(database: Database, record: dict) -> list[tuple[str, dict]]:
    if "attachments" in record:
        embedded = record
    else:
        embedded = _live_embedded(database, record["id"])
    rows = [("attachment", row) for row in embedded.get("attachments", [])]
    rows += [("material", row) for row in embedded.get("materials", [])]
    rows += [("case", row) for row in embedded.get("caseSources", [])]
    return rows


def _live_embedded(database: Database, case_id: str) -> dict:
    from app.modules.attachments.service import SNAPSHOT_FIELDS

    attachments = [
        {field: row[field] for field in SNAPSHOT_FIELDS if field in row}
        for row in database.attachments.find({"caseId": case_id})
    ]
    materials = list(database.case_materials.find({"caseId": case_id}))
    case_sources = list(database.case_sources.find({"caseId": case_id}))
    return {
        "attachments": attachments,
        "materials": materials,
        "caseSources": case_sources,
    }


def ordered_entries(
    database: Database, record: dict, user: dict | None, origin: str
) -> list[dict]:
    internal = is_internal(record, user)
    rows = _source_rows(database, record)
    ranks = _citation_ranks(record)
    entries = [
        _entry(database, source_type, row, user, origin, internal, record, ranks)
        for source_type, row in rows
    ]
    entries.sort(key=lambda item: item["_sort"])
    for number, entry in enumerate(entries, start=1):
        del entry["_sort"]
        entry["number"] = number
    return entries


def _citation_ranks(record: dict) -> dict[tuple[str | None, str | None], int]:
    """正文引用按首次出现顺序编号，未引用来源稳定排在引用来源之后。"""
    refs = citation_refs(record.get("document") or {})
    return {
        (ref["sourceType"], ref["sourceId"]): index for index, ref in enumerate(refs)
    }


def _base_entry(row: dict, rank: int) -> dict:
    entry_id = row.get("materialId") or row["id"]
    return {
        "sourceType": "attachment",
        "id": entry_id,
        "title": row.get("title") or row.get("name", ""),
        "source": row.get("source"),
        "version": None,
        "url": "",
        "contentAvailable": False,
        "_sort": (rank, row.get("createdAt") or "", entry_id),
    }


def _entry(
    database: Database, source_type: str, row: dict, user: dict | None,
    origin: str, internal: bool, record: dict, ranks: dict,
) -> dict:
    entry_id = row.get("materialId") or row["id"]
    entry = _base_entry(row, ranks.get((source_type, entry_id), len(ranks)))
    entry["sourceType"] = source_type
    entry["url"] = _entry_url(database, source_type, row, origin, record)
    entry["contentAvailable"] = _content_available(
        database, source_type, row, user, internal
    )
    if source_type == "case":
        entry["version"] = f"v{row['versionNumber']}"
        entry["source"], entry["publishedAt"] = _case_origin(database, row)
    return entry


def _content_available(
    database: Database, source_type: str, row: dict, user: dict | None, internal: bool
) -> bool:
    if source_type == "case":
        return source_case_content_available(database, row["sourceCaseId"], user)
    if source_type == "material":
        return can_read_material(_material_row(database, row), user)
    if internal:
        return True
    return _attachment_readable(row, user)


def _material_row(database: Database, row: dict) -> dict:
    if "createdBy" in row:
        return row
    live = database.materials.find_one({"id": row.get("materialId") or row["id"]})
    return {**row, **(live or {})}


def _attachment_readable(row: dict, user: dict | None) -> bool:
    level = row.get("accessLevel", "public")
    if level == "public":
        return True
    if level == "campus":
        return campus_verified(user)
    return False


def _entry_url(
    database: Database, source_type: str, row: dict, origin: str, record: dict
) -> str:
    if source_type == "case":
        return source_case_url(origin, row["sourceCaseId"], row["versionId"])
    if source_type == "material":
        return f"{origin}/api/materials/{row.get('materialId') or row['id']}/content"
    url = f"{origin}/api/cases/{row['caseId']}/attachments/{row['id']}/content"
    version_id = _containing_version_id(record)
    if version_id:
        url = f"{url}?versionId={version_id}"
    return url


def _containing_version_id(record: dict) -> str | None:
    """冻结版本记录携带 caseId，其附件链接必须定位该版本的快照内容。"""
    return record["id"] if "caseId" in record else None


def _case_origin(database: Database, row: dict) -> tuple[str | None, str | None]:
    version = database.case_versions.find_one(
        {"id": row["versionId"]}, {"metadata.author": 1, "metadata.organization": 1}
    )
    metadata = (version or {}).get("metadata", {})
    parts = [metadata.get("organization"), metadata.get("author")]
    label = "，".join(str(part) for part in parts if part)
    source = database.cases.find_one({"id": row["sourceCaseId"]}, {"publishedAt": 1})
    return (label or None), (source or {}).get("publishedAt")


def source_case_url(origin: str, source_case_id: str, version_id: str) -> str:
    return f"{origin}/#/cases/{source_case_id}?versionId={version_id}"
