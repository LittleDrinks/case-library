from __future__ import annotations

from app.modules.cases.service import (
    CASE_METADATA_FIELDS,
    CaseError,
    RevisionConflict,
)
from app.modules.ai.models import WorkbenchContext


CASE_CONTEXT_FIELDS = (
    "id",
    "title",
    "summary",
    "revision",
    "workflowStatus",
    "publicationStatus",
    "typeId",
    "typeName",
    "course",
    "author",
    "organization",
    "stageText",
    "audience",
    "purpose",
    "theoryPoints",
    "citations",
    "kit",
    "document",
)
ATTACHMENT_CONTEXT_FIELDS = (
    "id",
    "name",
    "mediaType",
    "size",
    "accessLevel",
    "searchText",
    "createdAt",
)
MATERIAL_CONTEXT_FIELDS = (
    "id",
    "materialId",
    "title",
    "summary",
    "source",
    "sourceUrl",
    "tags",
    "materialType",
    "authority",
    "accessLevel",
    "contentAvailable",
    "hasFile",
)


def _internal(case: dict, user: dict) -> bool:
    return user["role"] == "admin" or case["ownerId"] == user["id"]


def _authorized_case(database, case_id: str, user: dict) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "案例不存在")
    if not _internal(case, user):
        raise CaseError(403, "无权使用案例 AI")
    return case


def _check_revision(case: dict, revision: int) -> None:
    if case["revision"] != revision:
        raise RevisionConflict(case["revision"])


def _case_snapshot(case: dict) -> dict:
    snapshot = {field: case.get(field) for field in CASE_CONTEXT_FIELDS}
    snapshot["metadata"] = {
        field: case.get(field) for field in CASE_METADATA_FIELDS
    }
    return snapshot


def _attachment_snapshots(database, case_id: str) -> list[dict]:
    rows = database.attachments.find({"caseId": case_id}).sort("createdAt", 1)
    return [
        {field: row.get(field) for field in ATTACHMENT_CONTEXT_FIELDS} for row in rows
    ]


def _material_snapshot(row: dict, source: dict | None) -> dict:
    result = {field: row.get(field) for field in MATERIAL_CONTEXT_FIELDS}
    if source and source.get("excerpt"):
        result["excerpt"] = source["excerpt"]
    return result


def _material_snapshots(database, case_id: str) -> list[dict]:
    mounted = list(database.case_materials.find({"caseId": case_id}).sort("id", 1))
    ids = [row.get("materialId", row.get("id")) for row in mounted]
    sources = {row["id"]: row for row in database.materials.find({"id": {"$in": ids}})}
    return [_material_snapshot(row, sources.get(row.get("materialId", row.get("id")))) for row in mounted]


def _annotation(database, case_id: str, annotation_id: str | None) -> dict | None:
    if not annotation_id:
        return None
    row = database.annotations.find_one({"id": annotation_id, "caseId": case_id})
    if not row:
        raise CaseError(404, "批注不存在")
    return {key: value for key, value in row.items() if key != "_id"}


def _node_text(node: dict) -> str:
    if node.get("type") == "hardBreak":
        return "\n"
    return node.get("text", "") + "".join(
        _node_text(child) for child in node.get("content", [])
    )


def _pm_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _pm_slice(text: str, start: int, end: int) -> str:
    encoded = text.encode("utf-16-le")
    return encoded[start * 2 : end * 2].decode("utf-16-le")


def _node_size(node: dict) -> int:
    if node.get("type") == "text":
        return _pm_length(node.get("text", ""))
    if node.get("type") == "hardBreak":
        return 1
    return 2 + sum(_node_size(child) for child in node.get("content", []))


def _collect_spans(node: dict, start: int, top: int, spans: list[tuple]) -> None:
    if node.get("type") == "text":
        text = node.get("text", "")
        spans.append((start, start + _pm_length(text), top, text))
        return
    if node.get("type") == "hardBreak":
        spans.append((start, start + 1, top, "\n"))
        return
    cursor = start + 1
    for child in node.get("content", []):
        _collect_spans(child, cursor, top, spans)
        cursor += _node_size(child)


def _document_spans(document: dict) -> tuple[list[tuple], int]:
    spans, cursor = [], 0
    for index, node in enumerate(document.get("content", [])):
        _collect_spans(node, cursor, index, spans)
        cursor += _node_size(node)
    return spans, cursor


def _text_between(document: dict, start: int, end: int, separator: str) -> str:
    spans, size = _document_spans(document)
    if start < 0 or end > size or start >= end:
        raise CaseError(422, "AI 上下文位置无效")
    pieces, previous_top = [], None
    for span_start, span_end, top, text in spans:
        if span_end <= start or span_start >= end:
            continue
        left, right = max(start, span_start), min(end, span_end)
        if pieces and previous_top != top:
            pieces.append(separator)
        pieces.append(_pm_slice(text, left - span_start, right - span_start))
        previous_top = top
    return "".join(pieces)


def _finish_section(current: dict, end: int) -> dict:
    current["to"] = end
    current["text"] = "\n".join(current.pop("blocks")).strip()
    return current


def _new_section(node: dict, cursor: int, size: int) -> dict:
    return {
        "heading": _node_text(node).strip(),
        "from": cursor + _node_size(node),
        "to": size,
        "blocks": [],
    }


def _section_rows(document: dict) -> list[dict]:
    content = document.get("content", [])
    size, rows, current = sum(_node_size(node) for node in content), [], None
    cursor = 0
    for node in content:
        heading = node.get("type") == "heading" and node.get("attrs", {}).get("level") in {1, 2}
        if heading:
            if current:
                rows.append(_finish_section(current, cursor))
            current = _new_section(node, cursor, size)
        else:
            current = current or {"heading": "正文", "from": 0, "to": size, "blocks": []}
            current["blocks"].append(_node_text(node))
        cursor += _node_size(node)
    return rows + ([_finish_section(current, size)] if current else [])


def _match_section(document: dict, section) -> dict:
    expected = next(
        (
            row
            for row in _section_rows(document)
            if row["heading"] == section.heading
            and row["from"] == section.from_
            and row["to"] == section.to
        ),
        None,
    )
    if not expected or expected["text"] != section.text.strip():
        raise CaseError(422, "AI 小节上下文已变化")
    return expected


def _match_selection(document: dict, selection, section: dict | None) -> dict:
    if section and not (section["from"] <= selection.from_ < selection.to <= section["to"]):
        raise CaseError(422, "AI 选区不属于当前小节")
    text = _text_between(document, selection.from_, selection.to, " ")
    if text.strip() != selection.quote.strip():
        raise CaseError(422, "AI 选区原文已变化")
    return {"from": selection.from_, "to": selection.to, "quote": text}


def _targets(document: dict, context: WorkbenchContext) -> dict:
    section = _match_section(document, context.section) if context.section else None
    selection = _match_selection(document, context.selection, section) if context.selection else None
    return {key: value for key, value in (("section", section), ("selection", selection)) if value}


def _still_current(database, case_id: str, revision: int) -> None:
    current = database.cases.find_one({"id": case_id})
    if not current:
        raise CaseError(404, "案例不存在")
    _check_revision(current, revision)


def load_workbench_snapshot(
    database, case_id: str, context: WorkbenchContext, user: dict
) -> tuple[dict, dict]:
    case = _authorized_case(database, case_id, user)
    _check_revision(case, context.revision)
    snapshot = {
        "case": _case_snapshot(case),
        "attachments": _attachment_snapshots(database, case_id),
        "materials": _material_snapshots(database, case_id),
    }
    annotation = _annotation(database, case_id, context.annotationId)
    if annotation:
        snapshot["annotation"] = annotation
    _still_current(database, case_id, context.revision)
    return snapshot, _targets(case["document"], context)
