"""正文引用标记与资料区条目的关联完整性。"""
from __future__ import annotations

from pymongo.database import Database

from app.modules.cases.document_schema import citation_refs
from app.modules.cases.service import CaseError

SOURCE_COLLECTIONS = {
    "attachment": ("attachments", "id"),
    "material": ("case_materials", "materialId"),
    "case": ("case_sources", "id"),
}


def citation_ranks(document: dict) -> dict[tuple[str | None, str | None], int]:
    """正文引用按首次出现顺序编号，未引用来源稳定排在引用来源之后。"""
    refs = citation_refs(document or {})
    return {(ref["sourceType"], ref["sourceId"]): index for index, ref in enumerate(refs)}


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
        found = database[collection].count_documents(query, limit=1, session=session)
        if not found:
            raise CaseError(422, "正文引用的来源不在资料区")
