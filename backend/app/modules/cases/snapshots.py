from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.attachments.service import attachment_view, snapshot_attachments
from app.modules.case_materials.service import restore_materials, snapshot_materials
from app.modules.case_sources.service import (
    restore_case_sources,
    snapshot_case_sources,
)
from app.modules.cases.service import (
    CASE_METADATA_FIELDS,
    CaseError,
    RevisionConflict,
    case_metadata,
    internal_case_view,
)
from app.modules.cases.versions import FORMAL_VERSION_KINDS


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_draft_owner(case: dict, user: dict) -> None:
    if case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可覆盖工作稿")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "仅工作版本可执行覆盖")


def _record(
    case: dict, user: dict, attachments: list[dict], materials: list[dict],
    case_sources: list[dict], kind: str,
) -> dict:
    return {
        "id": f"cs-{secrets.token_hex(8)}",
        "caseId": case["id"],
        "kind": kind,
        "title": case["title"],
        "summary": case.get("summary", ""),
        "document": case["document"],
        "attachments": attachments,
        "materials": materials,
        "caseSources": case_sources,
        "metadata": case_metadata(case),
        "sourceRevision": case["revision"],
        "createdBy": user["id"],
        "createdAt": _now(),
    }


def _clean(snapshot: dict) -> dict:
    result = {key: value for key, value in snapshot.items() if key != "_id"}
    result["attachments"] = [attachment_view(row) for row in snapshot["attachments"]]
    result["materials"] = snapshot.get("materials", [])
    result["caseSources"] = snapshot.get("caseSources", [])
    return result


def _lock_case(database, case: dict, user: dict, session) -> dict:
    query = {
        "id": case["id"],
        "ownerId": user["id"],
        "workflowStatus": "draft",
        "revision": case["revision"],
    }
    locked = database.cases.find_one_and_update(
        query,
        {"$inc": {"snapshotRevision": 1}},
        session=session,
        return_document=ReturnDocument.AFTER,
    )
    if locked:
        return locked
    _raise_lock_conflict(database, case, user, session)


def _raise_lock_conflict(database, case: dict, user: dict, session) -> None:
    current = database.cases.find_one({"id": case["id"]}, session=session)
    if not current:
        raise CaseError(404, "案例不存在")
    _require_draft_owner(current, user)
    raise RevisionConflict(current["revision"])


def record_snapshot(database: Database, case: dict, user: dict, kind: str, session) -> dict:
    """在既有事务会话内留存一份批前快照，供写回类操作（如 Agent 接受）回滚。"""
    attachments = snapshot_attachments(database, case["id"], session)
    materials = snapshot_materials(database, case["id"], session)
    case_sources = snapshot_case_sources(database, case["id"], session)
    snapshot = _record(case, user, attachments, materials, case_sources, kind)
    database.case_snapshots.insert_one(snapshot, session=session)
    return _clean(snapshot)


def _overwrite_target(database, case_id: str, target_id: str, session) -> dict:
    """覆盖目标只能是本案例的正式提交或 AI 版本；跨案例一律 404。"""
    target = database.case_versions.find_one(
        {"id": target_id, "caseId": case_id,
         "kind": {"$in": list(FORMAL_VERSION_KINDS)}}, session=session
    )
    if not target:
        raise CaseError(404, "目标版本不存在")
    return target


def _clear_draft_annotations(database, case_id: str, session) -> None:
    """覆盖替换整篇工作稿；挂在工作稿上的旧批注随之清除，版本批注不受影响。"""
    database.annotations.delete_many(
        {"caseId": case_id, "versionId": None}, session=session
    )


def _restore_case(database, case: dict, target: dict, session) -> dict:
    fields = {key: target["metadata"].get(key) for key in CASE_METADATA_FIELDS}
    fields.update({key: target[key] for key in ("title", "summary", "document")})
    fields["updatedAt"] = _now()
    query = {
        "id": case["id"],
        "revision": case["revision"],
        "workflowStatus": "draft",
        "snapshotRevision": case["snapshotRevision"],
    }
    return database.cases.find_one_and_update(
        query,
        {"$set": fields, "$inc": {"revision": 1}},
        session=session,
        return_document=ReturnDocument.AFTER,
    )


def _restore_attachments(database, case_id: str, target: dict, session) -> None:
    database.attachments.delete_many({"caseId": case_id}, session=session)
    attachments = target["attachments"]
    if attachments:
        database.attachments.insert_many(attachments, session=session)


def _frozen_assets(database, case_id: str, session) -> tuple[list, list, list]:
    """冻结资料区三源：附件、素材与案例来源，供版本记录与覆盖共用。"""
    return (
        snapshot_attachments(database, case_id, session),
        snapshot_materials(database, case_id, session),
        snapshot_case_sources(database, case_id, session),
    )


def overwrite_draft(database: Database, case: dict, user: dict, target_id, session) -> dict:
    """用历史版本原子覆盖当前教师稿：不留版本、清工作稿旧批注，其余版本不变。"""
    _require_draft_owner(case, user)
    if not target_id:
        raise CaseError(422, "覆盖目标不能为空")
    target = _overwrite_target(database, case["id"], target_id, session)
    locked = _lock_case(database, case, user, session)
    before = _record(
        locked, user, *_frozen_assets(database, case["id"], session), "pre_overwrite",
    )
    database.case_snapshots.insert_one(before, session=session)
    restored = _restore_case(database, locked, target, session)
    if not restored:
        raise CaseError(409, "案例状态已变化")
    _restore_attachments(database, case["id"], target, session)
    restore_materials(database, case["id"], target, session)
    restore_case_sources(database, case["id"], target, session)
    _clear_draft_annotations(database, case["id"], session)
    return {"case": internal_case_view(restored, user), "snapshot": _clean(before)}
