from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.attachments.service import attachment_view, snapshot_attachments
from app.modules.case_materials.service import restore_materials, snapshot_materials
from app.modules.cases.service import (
    CASE_METADATA_FIELDS,
    CaseError,
    RevisionConflict,
    case_metadata,
    case_view,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_draft_owner(case: dict, user: dict) -> None:
    if case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可管理工作快照")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "仅工作版本可管理快照")


def _record(
    case: dict, user: dict, attachments: list[dict], materials: list[dict], kind: str
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
        "metadata": case_metadata(case),
        "sourceRevision": case["revision"],
        "createdBy": user["id"],
        "createdAt": _now(),
    }


def _clean(snapshot: dict) -> dict:
    result = {key: value for key, value in snapshot.items() if key != "_id"}
    result["attachments"] = [attachment_view(row) for row in snapshot["attachments"]]
    result["materials"] = snapshot.get("materials", [])
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


def create_snapshot(database: Database, case: dict, user: dict, session) -> dict:
    _require_draft_owner(case, user)
    locked = _lock_case(database, case, user, session)
    attachments = snapshot_attachments(database, case["id"], session)
    materials = snapshot_materials(database, case["id"], session)
    snapshot = _record(locked, user, attachments, materials, "manual")
    database.case_snapshots.insert_one(snapshot, session=session)
    return {"case": case_view(locked), "snapshot": _clean(snapshot)}


def _target(database, case_id: str, target_id: str, session) -> dict:
    query = {"id": target_id, "caseId": case_id}
    target = database.case_snapshots.find_one(query, session=session)
    target = target or database.case_versions.find_one(query, session=session)
    if not target:
        raise CaseError(404, "目标版本不存在")
    return target


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


def rollback_snapshot(
    database: Database, case: dict, user: dict, target_id: str | None, session
) -> dict:
    _require_draft_owner(case, user)
    if not target_id:
        raise CaseError(422, "回滚目标不能为空")
    target = _target(database, case["id"], target_id, session)
    locked = _lock_case(database, case, user, session)
    attachments = snapshot_attachments(database, case["id"], session)
    materials = snapshot_materials(database, case["id"], session)
    before = _record(locked, user, attachments, materials, "pre_rollback")
    database.case_snapshots.insert_one(before, session=session)
    restored = _restore_case(database, locked, target, session)
    if not restored:
        raise CaseError(409, "案例状态已变化")
    _restore_attachments(database, case["id"], target, session)
    restore_materials(database, case["id"], target, session)
    return {"case": case_view(restored), "snapshot": _clean(before)}


def list_snapshots(database: Database, case_id: str) -> list[dict]:
    rows = database.case_snapshots.find({"caseId": case_id}).sort("createdAt", 1)
    return [_clean(row) for row in rows]
