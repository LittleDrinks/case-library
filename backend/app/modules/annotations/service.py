from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.agent import prosemirror
from app.modules.cases.service import CaseError, RevisionConflict


ANCHOR_FIELDS = ("from", "to", "quoteHash", "revision")
ACTIVE_ANCHOR = "active"
CHANGED_ANCHOR = "changed"
DELETED_ANCHOR = "deleted"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _view(annotation: dict) -> dict:
    view = {key: value for key, value in annotation.items() if key != "_id"}
    view.pop("updatedAt", None)
    if view.pop("_legacy", False):
        for field in ANCHOR_FIELDS:
            view.pop(field, None)
    elif view.get("versionId") is None:
        view.setdefault("anchorState", ACTIVE_ANCHOR)
    return view


def _find(collection, query: dict, session=None):
    options = {"session": session} if session is not None else {}
    return collection.find_one(query, **options)


def _case(database: Database, case_id: str, user: dict, session=None) -> dict:
    case = _find(database.cases, {"id": case_id}, session)
    if not case:
        raise CaseError(404, "案例不存在")
    if user["role"] != "admin" and case["ownerId"] != user["id"]:
        raise CaseError(403, "无权查看案例批注")
    return case


def _review_version(database: Database, case: dict, session=None) -> dict:
    version = _find(
        database.case_versions,
        {"id": case.get("submittedVersionId"), "caseId": case["id"]},
        session,
    )
    if case["workflowStatus"] != "reviewing" or not version:
        raise CaseError(409, "仅审核中的版本可添加批注")
    return version


def _utf16_size(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _utf16_slice(value: str, left: int, right: int) -> str:
    encoded = value.encode("utf-16-le")
    return encoded[left * 2:right * 2].decode("utf-16-le")


def _node_size(node: dict) -> int:
    if node.get("text") is not None:
        return _utf16_size(node["text"])
    children = node.get("content", [])
    return 1 if not children else 2 + sum(_node_size(child) for child in children)


def _node_text(node: dict) -> str:
    return node.get("text", "") + "".join(
        _node_text(child) for child in node.get("content", [])
    )


def _append_text_blocks(node: dict, start: int, section: str, blocks: list[dict]) -> None:
    size = _node_size(node)
    if node.get("type") in {"paragraph", "heading"}:
        blocks.append({"node": node, "start": start, "end": start + size - 1, "section": section})
    offset = start + 1
    for child in node.get("content", []):
        _append_text_blocks(child, offset, section, blocks)
        offset += _node_size(child)


def _text_blocks(document: dict) -> list[dict]:
    blocks, offset, section = [], 0, "正文"
    for node in document.get("content", []):
        if node.get("type") == "heading" and node.get("attrs", {}).get("level") in {1, 2}:
            section = _node_text(node).strip() or "未命名小节"
        _append_text_blocks(node, offset, section, blocks)
        offset += _node_size(node)
    return blocks


def _range_text(node: dict, start: int, lower: int, upper: int) -> str:
    if node.get("text") is not None:
        left, right = max(lower, start), min(upper, start + _utf16_size(node["text"]))
        return _utf16_slice(node["text"], left - start, right - start) if left < right else ""
    cursor, parts = start + 1, []
    for child in node.get("content", []):
        parts.append(_range_text(child, cursor, lower, upper))
        cursor += _node_size(child)
    return "".join(parts)


def _validated_range_text(node: dict, start: int, lower: int, upper: int) -> str:
    try:
        return _range_text(node, start, lower, upper)
    except UnicodeDecodeError as error:
        raise CaseError(409, "批注选区必须使用有效的正文位置") from error


def _anchor_values(body: dict) -> tuple[int | None, int | None, str | None, int | None]:
    return tuple(body.get(field) for field in ANCHOR_FIELDS)


def _require_anchor(document: dict, body: dict) -> None:
    start, end, quote_hash, revision = _anchor_values(body)
    if None in (start, end, quote_hash, revision):
        raise CaseError(409, "批注锚点字段不完整")
    block = next((row for row in _text_blocks(document) if row["start"] < start <= row["end"] and row["start"] < end <= row["end"]), None)
    quote = body["quote"]
    if not block or end <= start:
        raise CaseError(409, "批注选区必须位于同一正文段落")
    actual = _validated_range_text(block["node"], block["start"], start, end)
    if block["section"] != body["section"].strip() or actual != quote:
        raise CaseError(409, "批注选区已变化，请重新选择正文")
    if hashlib.sha256(quote.encode("utf-8")).hexdigest() != quote_hash:
        raise CaseError(409, "批注引用校验失败，请重新选择正文")


def _mapping_for_change(document: dict, updated: dict, steps: list[dict] | None):
    if document == updated and not steps:
        return None
    if steps is None:
        raise CaseError(409, "正文位置映射缺失，请重新保存")
    if not steps:
        raise CaseError(409, "正文位置映射缺失，请重新保存")
    try:
        applied, mapping = prosemirror.apply_steps(document, steps)
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise CaseError(409, "正文位置映射无效，请重新保存") from error
    if applied != updated:
        raise CaseError(409, "正文变更与位置映射不一致，请重新保存")
    return mapping


def document_mapping(document: dict, updated: dict, steps: list[dict] | None):
    return _mapping_for_change(document, updated, steps)


def _has_replacement(mapping, start: int, end: int) -> bool:
    left, right = start, end
    for step_map in mapping.maps:
        for position, old_size, new_size in zip(
            step_map.ranges[::3], step_map.ranges[1::3], step_map.ranges[2::3]
        ):
            overlaps = old_size and max(left, position) < min(right, position + old_size)
            inserted_at_collapsed = left == right == position and old_size == 0
            if new_size and (overlaps or inserted_at_collapsed):
                return True
        left = step_map.map(left, 1)
        right = step_map.map(right, -1)
    return False


def _deleted_by_mapping(mapping, start: int, end: int) -> bool:
    left = mapping.map_result(start, 1)
    right = mapping.map_result(end, -1)
    return left.pos == right.pos and left.deleted and right.deleted and not _has_replacement(
        mapping, start, end
    )


def _mapped_anchor(document: dict, annotation: dict, mapping) -> tuple[str, dict | None]:
    start, end = annotation.get("from"), annotation.get("to")
    if not isinstance(start, int) or not isinstance(end, int) or start >= end:
        return CHANGED_ANCHOR, None
    mapped_start = mapping.map(start, 1)
    mapped_end = mapping.map(end, -1)
    if _deleted_by_mapping(mapping, start, end):
        return DELETED_ANCHOR, None
    if mapped_start >= mapped_end:
        return CHANGED_ANCHOR, None
    row = _anchor_at(document, mapped_start, mapped_end)
    if not row or row["quote"] != annotation.get("quote"):
        return CHANGED_ANCHOR, None
    return ACTIVE_ANCHOR, row


def _anchor_at(document: dict, start: int, end: int) -> dict | None:
    block = next((row for row in _text_blocks(document)
                  if row["start"] < start <= row["end"] and row["start"] < end <= row["end"]), None)
    if not block or end <= start:
        return None
    return {
        "from": start, "to": end, "quote": _range_text(block["node"], block["start"], start, end),
        "section": block["section"],
    }


def _set_anchor_state(database, row: dict, state: str, anchor: dict | None, revision: int, session) -> None:
    changes = {"anchorState": state, "revision": revision}
    unset = {}
    if anchor:
        changes.update(anchor)
    else:
        unset.update({"from": "", "to": ""})
    database.annotations.update_one(
        {"id": row["id"], "caseId": row["caseId"]},
        {"$set": changes, **({"$unset": unset} if unset else {})},
        session=session,
    )


def _reconcile_pending_artifact(
    database, row: dict, document: dict, mapping, revision: int, session
) -> None:
    state, anchor = _mapped_anchor(document, row["target"], mapping)
    if state == ACTIVE_ANCHOR and anchor:
        target = {"from": anchor["from"], "to": anchor["to"], "quote": row["target"]["quote"]}
        database.agent_artifacts.update_one(
            {"id": row["id"], "status": "pending"},
            {"$set": {"baseRevision": revision, "target": target}},
            session=session,
        )
        return
    database.agent_artifacts.update_one(
        {"id": row["id"], "status": "pending"},
        {"$set": {"status": "expired"}},
        session=session,
    )


def _reconcile_pending_artifacts(
    database, case_id: str, document: dict, mapping, revision: int, session,
    exclude_artifact_id: str | None,
) -> None:
    rows = database.agent_artifacts.find({"caseId": case_id, "status": "pending"}, session=session)
    for row in rows:
        if row["id"] != exclude_artifact_id:
            _reconcile_pending_artifact(database, row, document, mapping, revision, session)


def reconcile_document_annotations(
    database: Database, case_id: str, document: dict, updated: dict,
    revision: int, steps: list[dict] | None, session=None, mapping=None,
    exclude_artifact_id: str | None = None,
) -> None:
    if mapping is None:
        mapping = _mapping_for_change(document, updated, steps)
    if mapping is None:
        return
    rows = database.annotations.find({"caseId": case_id, "versionId": None}, session=session)
    for row in rows:
        if row.get("anchorState", ACTIVE_ANCHOR) != ACTIVE_ANCHOR:
            continue
        state, anchor = _mapped_anchor(updated, row, mapping)
        _set_anchor_state(database, row, state, anchor, revision, session)
    _reconcile_pending_artifacts(
        database, case_id, updated, mapping, revision, session, exclude_artifact_id,
    )


def _section_texts(document: dict) -> dict[str, str]:
    sections, current = {}, ""
    for node in document.get("content", []):
        if node.get("type") == "heading" and node.get("attrs", {}).get("level") in {1, 2}:
            current = _node_text(node).strip()
            sections[current] = current
        elif current:
            sections[current] += _node_text(node)
    return sections


def _require_legacy_anchor(version: dict, body: dict) -> None:
    section_text = _section_texts(version["document"]).get(body["section"], "")
    if body["quote"].strip() not in section_text:
        raise CaseError(409, "批注选区不属于待审版本小节")


def _target_document(database, case: dict, body: dict, user: dict, session):
    if body["source"] == "admin":
        if user["role"] != "admin":
            raise CaseError(403, "仅管理员可添加人工审核批注")
        version = _review_version(database, case, session)
        return version["document"], version["id"]
    if body["source"] != "manual" or case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可添加手动批注")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "仅草稿案例可添加手动批注")
    return case["document"], None


def _touch_case(database, case: dict, session) -> None:
    updated = database.cases.find_one_and_update(
        {"id": case["id"], "revision": case["revision"]},
        {"$set": {"updatedAt": _now()}},
        session=session,
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return
    current = database.cases.find_one({"id": case["id"]})
    raise RevisionConflict(current["revision"])


def _annotation(case: dict, body: dict, user: dict, version_id: str | None) -> dict:
    return {
        "id": f"an-{secrets.token_hex(8)}",
        "caseId": case["id"],
        "versionId": version_id,
        **body,
        "status": "pending",
        "replies": [],
        "createdBy": user["id"],
        "createdAt": _now(),
    }


def _create_in_transaction(database, case_id: str, body: dict, user: dict, session) -> dict:
    case = _case(database, case_id, user, session)
    document, version_id = _target_document(database, case, body, user, session)
    legacy = body.get("revision") is None
    if not legacy and body["revision"] != case["revision"]:
        raise RevisionConflict(case["revision"])
    if legacy:
        _require_legacy_anchor({"document": document}, body)
    else:
        _require_anchor(document, body)
    _touch_case(database, case, session)
    annotation = _annotation(case, body, user, version_id)
    if legacy:
        annotation["_legacy"] = True
    database.annotations.insert_one(annotation, session=session)
    return _view(annotation)


def _transaction(database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(lambda active: callback(active))


def create_annotation(database: Database, case_id: str, body: dict, user: dict) -> dict:
    return _transaction(
        database,
        lambda session: _create_in_transaction(database, case_id, body, user, session),
    )


def list_annotations(database: Database, case_id: str, user: dict) -> list[dict]:
    _case(database, case_id, user)
    rows = database.annotations.find({"caseId": case_id}).sort("createdAt", 1)
    return [_view(row) for row in rows]


def _get_annotation(database: Database, case_id: str, annotation_id: str) -> dict:
    annotation = database.annotations.find_one({"id": annotation_id, "caseId": case_id})
    if not annotation:
        raise CaseError(404, "批注不存在")
    return annotation


def _require_editor(annotation: dict, user: dict) -> None:
    if annotation["createdBy"] != user["id"]:
        raise CaseError(403, "仅批注作者可编辑或删除")
    if annotation["status"] != "pending":
        raise CaseError(409, "已解决批注不可编辑或删除")


def update_annotation(database: Database, case_id: str, annotation_id: str, content: str, user: dict) -> dict:
    _case(database, case_id, user)
    annotation = _get_annotation(database, case_id, annotation_id)
    _require_editor(annotation, user)
    updated = database.annotations.find_one_and_update(
        {"id": annotation_id, "caseId": case_id, "createdBy": user["id"], "status": "pending"},
        {"$set": {"content": content, "updatedAt": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise CaseError(409, "批注状态已变化")
    return _view(updated)


def delete_annotation(database: Database, case_id: str, annotation_id: str, user: dict) -> None:
    _case(database, case_id, user)
    annotation = _get_annotation(database, case_id, annotation_id)
    _require_editor(annotation, user)
    deleted = database.annotations.delete_one(
        {"id": annotation_id, "caseId": case_id, "createdBy": user["id"], "status": "pending"}
    )
    if deleted.deleted_count != 1:
        raise CaseError(409, "批注状态已变化")


def add_reply(
    database: Database, case_id: str, annotation_id: str, content: str, user: dict
) -> dict:
    _case(database, case_id, user)
    _get_annotation(database, case_id, annotation_id)
    reply = {
        "id": f"ar-{secrets.token_hex(8)}",
        "content": content,
        "createdBy": user["id"],
        "createdAt": _now(),
    }
    updated = database.annotations.find_one_and_update(
        {"id": annotation_id, "caseId": case_id},
        {"$push": {"replies": reply}},
        return_document=ReturnDocument.AFTER,
    )
    return _view(updated)


def _require_status_actor(case: dict, user: dict, status: str) -> None:
    if status == "resolved" and case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可解决批注")
    if status == "pending" and user["role"] != "admin":
        raise CaseError(403, "仅管理员可重开批注")


def change_status(
    database: Database, case_id: str, annotation_id: str, status: str, user: dict
) -> dict:
    case = _case(database, case_id, user)
    _get_annotation(database, case_id, annotation_id)
    _require_status_actor(case, user, status)
    expected = "pending" if status == "resolved" else "resolved"
    updated = database.annotations.find_one_and_update(
        {"id": annotation_id, "caseId": case_id, "status": expected},
        {"$set": {"status": status}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise CaseError(409, "批注状态已变化")
    return _view(updated)
