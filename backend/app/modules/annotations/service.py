from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.agent import prosemirror
from app.modules.cases.service import CaseError, RevisionConflict, case_view

ANCHOR_FIELDS = ("from", "to", "quoteHash", "revision")
ACTIVE_ANCHOR = "active"
CHANGED_ANCHOR = "changed"
DELETED_ANCHOR = "deleted"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _revision_is_valid(annotation: dict, revision: dict, case_revision: int) -> bool:
    target = revision.get("target") or {}
    return (
        annotation.get("status") == "pending"
        and annotation.get("anchorState", ACTIVE_ANCHOR) == ACTIVE_ANCHOR
        and revision.get("baseRevision") == case_revision
        and target.get("from") == annotation.get("from")
        and target.get("to") == annotation.get("to")
        and target.get("quote") == annotation.get("quote")
    )


def _revision_view(annotation: dict, revision: dict, case_revision: int) -> dict:
    view = {key: value for key, value in revision.items() if key != "_id"}
    if view.get("status") == "pending" and not _revision_is_valid(annotation, revision, case_revision):
        view["status"] = "expired"
    return view


def _view(annotation: dict, case_revision: int) -> dict:
    view = {key: value for key, value in annotation.items() if key != "_id"}
    view.pop("updatedAt", None)
    if view.pop("_legacy", False):
        for field in ANCHOR_FIELDS:
            view.pop(field, None)
    elif view.get("versionId") is None:
        view.setdefault("anchorState", ACTIVE_ANCHOR)
    if "revisions" in view:
        view["revisions"] = [
            _revision_view(annotation, row, case_revision) for row in view["revisions"]
        ]
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
    if node.get("type") == "hardBreak":
        return "\n"
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
    if node.get("type") == "hardBreak":
        return "\n" if lower <= start < upper else ""
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
        revisions = _map_revision_targets(row, anchor, revision)
        if revisions is not None:
            changes["revisions"] = revisions
    else:
        unset.update({"from": "", "to": ""})
    database.annotations.update_one(
        {"id": row["id"], "caseId": row["caseId"]},
        {"$set": changes, **({"$unset": unset} if unset else {})},
        session=session,
    )


def _map_revision_targets(row: dict, anchor: dict, case_revision: int) -> list[dict] | None:
    if "revisions" not in row:
        return None
    return [
        {**revision, "baseRevision": case_revision, "target": {
            **revision.get("target", {}), "from": anchor["from"], "to": anchor["to"]
        }}
        if revision.get("status") == "pending" and revision.get("target", {}).get("quote") == row.get("quote")
        else revision
        for revision in row["revisions"]
    ]


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
    current = database.cases.find_one({"id": case["id"]}, session=session)
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
    return _view(annotation, case["revision"])


def _transaction(database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(lambda active: callback(active))


def create_annotation(database: Database, case_id: str, body: dict, user: dict) -> dict:
    return _transaction(
        database,
        lambda session: _create_in_transaction(database, case_id, body, user, session),
    )


def list_annotations(database: Database, case_id: str, user: dict) -> list[dict]:
    case = _case(database, case_id, user)
    rows = database.annotations.find(_list_query(case, user)).sort("createdAt", 1)
    return [_view(row, case["revision"]) for row in rows]


def _list_query(case: dict, user: dict) -> dict:
    """私人讨论仅案例作者可见；管理员只读版本绑定的审核批注，不泄漏个人修订。"""
    if case["ownerId"] == user["id"]:
        return {"caseId": case["id"]}
    return {"caseId": case["id"], "versionId": {"$ne": None}}


def _get_annotation(database: Database, case_id: str, annotation_id: str, session=None) -> dict:
    annotation = _find(database.annotations, {"id": annotation_id, "caseId": case_id}, session)
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
    return _view(updated, _case(database, case_id, user)["revision"])

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
    case = _case(database, case_id, user)
    annotation = _get_annotation(database, case_id, annotation_id)
    _require_reply_actor(case, annotation, user)
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
    return _view(updated, _case(database, case_id, user)["revision"])

def _require_reply_actor(case: dict, annotation: dict, user: dict) -> None:
    """私人批注（版本未绑定）只有作者能回复；审核批注允许作者与管理员讨论。"""
    if annotation.get("versionId") is not None:
        return
    if annotation.get("createdBy") != user["id"] or case["ownerId"] != user["id"]:
        raise CaseError(403, "仅批注作者可回复私人讨论")


def _require_status_actor(case: dict, annotation: dict, user: dict, status: str) -> None:
    if annotation.get("versionId") is None:
        if case["ownerId"] != user["id"] or annotation.get("createdBy") != user["id"]:
            raise CaseError(403, "仅私人批注作者可改变状态")
        return
    if status == "resolved" and case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可解决批注")
    if status == "pending" and user["role"] != "admin":
        raise CaseError(403, "仅管理员可重开批注")


def change_status(
    database: Database, case_id: str, annotation_id: str, status: str, user: dict
) -> dict:
    return _transaction(
        database,
        lambda session: _change_status(
            database, case_id, annotation_id, status, user, session
        ),
    )


def _change_status(database, case_id, annotation_id, status, user, session):
    case = _case(database, case_id, user, session)
    annotation = _get_annotation(database, case_id, annotation_id, session)
    _require_status_actor(case, annotation, user, status)
    expected = "pending" if status == "resolved" else "resolved"
    update = {"$set": {"status": status}}
    if status == "resolved":
        update["$set"]["revisions"] = _closed_revisions(annotation)
    updated = database.annotations.find_one_and_update(
        {"id": annotation_id, "caseId": case_id, "status": expected},
        update, return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "批注状态已变化")
    _decide_linked_artifacts(database, annotation, user, "rejected", session)
    return _view(updated, case["revision"])


def _closed_revisions(annotation: dict) -> list[dict]:
    return [
        {**revision, "status": "rejected" if revision.get("status") == "pending" else revision.get("status")}
        for revision in annotation.get("revisions", [])
    ]


def _decide_linked_artifacts(
    database, annotation, user, decision, session, selected_id=None, only_ids=None,
) -> None:
    for revision in annotation.get("revisions", []):
        if only_ids is not None and revision.get("id") not in only_ids:
            continue
        artifact_decision = decision
        if selected_id and revision.get("id") != selected_id:
            artifact_decision = "expired"
        _decide_artifact(
            database, revision.get("artifactId"), user, artifact_decision, session,
        )


def _decide_artifact(database, artifact_id, user, decision: str, session) -> None:
    from app.modules.agent.repository import AgentRepository

    artifact = database.agent_artifacts.find_one_and_update(
        {"id": artifact_id, "status": "pending"},
        {"$set": {"status": decision, "decidedBy": user["id"], "decidedAt": _now()}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if artifact:
        AgentRepository(database)._append_event(
            artifact["threadId"], "artifact.decided", artifact["runId"],
            {"artifactId": artifact["id"], "decision": decision}, session,
        )


def record_ai_revision(database, artifact, created_by: str, session=None) -> dict | None:
    annotation_id = getattr(artifact, "annotation_id", None)
    if not annotation_id:
        return None
    revision = _revision_document(artifact, created_by)
    query = _revision_query(annotation_id, artifact, created_by, revision["target"])
    updated = database.annotations.find_one_and_update(
        query, {"$push": {"revisions": revision}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "批注选区已变化，不能保存 AI 修订")
    return revision


def _revision_document(artifact, created_by: str) -> dict:
    target = artifact.target.model_dump(by_alias=True)
    return {
        "id": new_revision_id(), "artifactId": artifact.id, "runId": artifact.run_id,
        "baseRevision": artifact.base_revision, "target": target,
        "replacement": artifact.replacement, "reason": artifact.reason,
        "status": "pending", "createdBy": created_by, "createdAt": _now(),
    }


def _revision_query(annotation_id: str, artifact, created_by: str, target: dict) -> dict:
    return {
        "id": annotation_id, "caseId": artifact.case_id, "createdBy": created_by,
        "status": "pending",
        "from": target["from"], "to": target["to"], "quote": target["quote"],
        "$or": [{"anchorState": ACTIVE_ANCHOR}, {"anchorState": {"$exists": False}}],
    }


def mark_ai_revision_decision(database, artifact, user: dict, decision: str, session=None) -> None:
    if not artifact.annotation_id:
        return
    annotation = _find(
        database.annotations,
        {"id": artifact.annotation_id, "caseId": artifact.case_id},
        session,
    )
    revisions = _decided_revisions(annotation, artifact, user, decision)
    database.annotations.update_one(
        {"id": annotation["id"], "status": "pending"},
        {"$set": {"revisions": revisions}}, session=session,
    )


def _decided_revisions(annotation, artifact, user: dict, decision: str) -> list[dict]:
    if not annotation or annotation.get("createdBy") != user["id"]:
        raise CaseError(403, "仅批注作者可决定修订")
    revisions = [
        {**revision, "status": decision if revision.get("artifactId") == artifact.id
         else revision.get("status")}
        for revision in annotation.get("revisions", [])
    ]
    if not any(revision.get("artifactId") == artifact.id for revision in revisions):
        raise CaseError(409, "批注修订已变化")
    return revisions


def new_revision_id() -> str:
    return f"arv-{secrets.token_hex(8)}"


@dataclass
class MergeRejected:
    """合并被拒绝且无正文写入；过期状态在独立事务中持久化后以 409 返回。"""

    reason: str = "没有可合并的有效 AI 修订"


def merge_annotation(database: Database, case_id: str, annotation_id: str, user: dict) -> dict:
    outcome = _transaction(
        database,
        lambda session: _merge_annotation(database, case_id, annotation_id, user, session),
    )
    if isinstance(outcome, MergeRejected):
        _transaction(
            database,
            lambda active: _expire_invalid_revisions(database, case_id, annotation_id, user, active),
        )
        raise CaseError(409, outcome.reason)
    return outcome


def _merge_annotation(database, case_id, annotation_id, user, session):
    case = _case(database, case_id, user, session)
    annotation = _get_annotation(database, case_id, annotation_id, session)
    _require_merge_owner(case, annotation, user)
    if annotation["status"] == "resolved":
        return {"annotation": _view(annotation, case["revision"]), "case": case_view(case)}
    revision = _latest_valid_revision(database, annotation, case["revision"], session)
    if revision is None:
        return MergeRejected()
    return _commit_annotation_merge(database, case, annotation, revision, user, session)


def _require_merge_owner(case: dict, annotation: dict, user: dict) -> None:
    if case["ownerId"] != user["id"] or annotation["createdBy"] != user["id"]:
        raise CaseError(403, "仅批注作者可合并修订")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "案例当前不可编辑")


def _latest_valid_revision(database, annotation, case_revision: int, session) -> dict | None:
    for revision in reversed(annotation.get("revisions", [])):
        if revision.get("status") == "pending" and _revision_mergeable(
            database, annotation, revision, case_revision, session,
        ):
            return revision
    return None


def _expire_invalid_revisions(database, case_id: str, annotation_id: str, user: dict, session) -> None:
    """过期事务内重新读取：只失效当前确实失效的候选，保留期间新增的有效修订。"""
    case = _case(database, case_id, user, session)
    annotation = _get_annotation(database, case_id, annotation_id, session)
    _require_merge_owner(case, annotation, user)
    if annotation.get("status") != "pending":
        return
    stale_ids = [
        revision["id"] for revision in annotation.get("revisions", [])
        if revision.get("status") == "pending" and not _revision_mergeable(
            database, annotation, revision, case["revision"], session,
        )
    ]
    if stale_ids:
        _expire_stale_revisions(database, annotation, user, stale_ids, session)


def _expire_stale_revisions(database, annotation, user, stale_ids: list[str], session) -> None:
    database.annotations.update_one(
        {"id": annotation["id"], "status": "pending"},
        {"$set": {"revisions": [
            {**revision, "status": "expired"}
            if revision.get("id") in stale_ids else revision
            for revision in annotation.get("revisions", [])
        ]}},
        session=session,
    )
    _decide_linked_artifacts(database, annotation, user, "expired", session, only_ids=stale_ids)


def _revision_mergeable(database, annotation, revision, case_revision: int, session) -> bool:
    if not _revision_is_valid(annotation, revision, case_revision):
        return False
    artifact = _find(database.agent_artifacts, {"id": revision.get("artifactId")}, session)
    return bool(
        artifact and artifact.get("status") == "pending"
        and artifact.get("baseRevision") == case_revision
    )


def _commit_annotation_merge(database, case, annotation, revision, user, session):
    document, steps = _merged_document(case, annotation, revision)
    from app.modules.cases.snapshots import record_snapshot

    mapping = _mapping_for_change(case["document"], document, steps)
    record_snapshot(database, case, user, "pre_annotation_merge", session)
    updated_case = _commit_case_document(database, case, document, session)
    reconcile_document_annotations(
        database, case["id"], case["document"], document, updated_case["revision"],
        steps, session, mapping, exclude_artifact_id=revision["artifactId"],
    )
    updated_annotation = _finish_annotation_merge(
        database, annotation, revision, user, session,
    )
    return {
        "annotation": _view(updated_annotation, updated_case["revision"]),
        "case": case_view(updated_case),
    }


def _merged_document(case: dict, annotation: dict, revision: dict):
    try:
        return prosemirror.replaced_document_with_steps(
            case["document"], annotation["from"], annotation["to"],
            annotation["quote"], revision["replacement"],
        )
    except (prosemirror.ParagraphChangedError, prosemirror.ParagraphNotFoundError) as error:
        raise CaseError(409, "目标选区原文已变化，修订候选已过期") from error


def _commit_case_document(database, case, document, session):
    updated = database.cases.find_one_and_update(
        {"id": case["id"], "ownerId": case["ownerId"], "workflowStatus": "draft",
         "revision": case["revision"]},
        {"$set": {"document": document, "updatedAt": _now()}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "案例状态已变化")
    return updated


def _finish_annotation_merge(database, annotation, selected, user, session):
    revisions = [
        {**revision, "status": "accepted" if revision["id"] == selected["id"]
         else "expired" if revision.get("status") == "pending" else revision.get("status")}
        for revision in annotation.get("revisions", [])
    ]
    updated = database.annotations.find_one_and_update(
        {"id": annotation["id"], "status": "pending"},
        {"$set": {"status": "resolved", "revisions": revisions}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise CaseError(409, "批注状态已变化")
    _decide_linked_artifacts(database, annotation, user, "accepted", session, selected["id"])
    return updated
