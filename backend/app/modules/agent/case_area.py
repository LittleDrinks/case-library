"""Build the current case-area source list and validate selected source parts."""

from __future__ import annotations

from pymongo.database import Database

from app.modules.agent.models import SourceRef
from app.modules.cases.published import version_readable
from app.modules.cases.sources import ordered_entries
from app.modules.cases.service import CaseError

SOURCE_TYPES = ("attachment", "material", "case")


def area_rows(database: Database, case_id: str, version_id: str | None = None) -> dict[str, list[dict]]:
    if version_id:
        version = database.case_versions.find_one({"id": version_id, "caseId": case_id})
        return _embedded_rows(version or {})
    return {
        "attachment": list(database.attachments.find({"caseId": case_id}).sort("createdAt", 1)),
        "material": list(database.case_materials.find({"caseId": case_id}).sort("id", 1)),
        "case": list(database.case_sources.find({"caseId": case_id}).sort("id", 1)),
    }


def retained_sources(
    database: Database, case_id: str, user: dict | None = None,
    version_id: str | None = None,
) -> list[SourceRef]:
    record = _catalog_record(database, case_id, version_id)
    refs = [_ref(kind, row, case_id) for kind in SOURCE_TYPES
            for row in record.get(_field(kind), [])]
    by_key = {(ref.kind, ref.id): ref for ref in refs}
    entries = ordered_entries(database, record, user, "")
    return [by_key[(entry["sourceType"], entry["id"])] for entry in entries]


def _field(kind: str) -> str:
    return {"attachment": "attachments", "material": "materials", "case": "caseSources"}[kind]


def _embedded_rows(record: dict) -> dict[str, list[dict]]:
    return {"attachment": record.get("attachments", []),
            "material": record.get("materials", []),
            "case": record.get("caseSources", [])}


def _catalog_record(database, case_id: str, version_id: str | None) -> dict:
    case = database.cases.find_one({"id": case_id}) or {"id": case_id}
    if not version_id:
        rows = area_rows(database, case_id)
        return {**case, "attachments": rows["attachment"],
                "materials": rows["material"], "caseSources": rows["case"]}
    version = database.case_versions.find_one({"id": version_id, "caseId": case_id})
    if not version or not version_readable(database, case, version_id, version, False):
        return {"id": version_id, "caseId": case_id, "document": {},
                "attachments": [], "materials": [], "caseSources": []}
    return {"id": version_id, "caseId": case_id, "document": version.get("document", {}),
            **_embedded_rows(version)}


def _ref(kind: str, row: dict, case_id: str) -> SourceRef:
    source_id = row.get("materialId") or row["id"]
    if kind == "attachment":
        return SourceRef(kind=kind, id=row["id"], title=row.get("name") or "",
                         location=f"attachment:{case_id}/{row['id']}")
    if kind == "material":
        return SourceRef(kind=kind, id=source_id, title=row.get("title") or "",
                         location=f"material:{source_id}")
    return SourceRef(
        kind=kind, id=row["id"], title=row.get("title") or "",
        version=f"v{row['versionNumber']}" if row.get("versionNumber") else None,
        version_id=row.get("versionId"),
        location=f"case:{row.get('sourceCaseId')}@{row.get('versionId')}",
    )


def selection_from_parts(
    database: Database, case_id: str, parts: list[dict], version_id: str | None = None
) -> list[dict]:
    refs = retained_sources(database, case_id, version_id=version_id)
    selected = []
    for part in parts:
        if part.get("type") != "data-source":
            continue
        selected.append(_selected_ref(refs, part.get("data")))
    return selected


def _selected_ref(refs: list[SourceRef], data: object) -> dict:
    if not isinstance(data, dict):
        raise CaseError(422, "来源选区格式无效")
    kind, source_id = data.get("sourceType"), data.get("id")
    if kind not in SOURCE_TYPES or not isinstance(source_id, str) or not source_id:
        raise CaseError(422, "来源选区格式无效")
    if not any(ref.kind == kind and ref.id == source_id for ref in refs):
        raise CaseError(422, "所选来源不在当前案例资料区")
    return {"sourceType": kind, "id": source_id}


def catalog_instructions(title: str, refs: list[SourceRef], selected: list[dict],
                         selections: list[dict]) -> str:
    lines = [f"## 当前案例资料区（{title}）", "按需调用 read_source 读取以下保留来源："]
    lines += [f"- [{ref.kind}] {ref.title}（id: {ref.id}）" for ref in refs]
    chosen = ", ".join(item["id"] for item in selected) or "无"
    lines += [f"本条消息点选来源：{chosen}", _selection_line(selections)]
    return "\n".join(lines)


def _selection_line(selections: list[dict]) -> str:
    if not selections:
        return "本条消息没有正文选区。"
    return "本条消息正文选区：" + "；".join(item["quote"] for item in selections)


def ref_view(ref: SourceRef) -> dict:
    return ref.model_dump(by_alias=True, exclude_none=True)
