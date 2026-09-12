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
from app.modules.cases.versions import (
    FORMAL_VERSION_KINDS,
    MANUAL_VERSION_KIND,
    RESTORE_VERSION_KIND,
    create_version,
    restore_draft_annotations,
    snapshot_annotations,
)


RESTORE_BASELINE_TITLE = "恢复前的当前稿"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_draft_owner(case: dict, user: dict) -> None:
    if case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可恢复工作稿")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "仅工作版本可执行恢复")


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
    snapshot["annotations"] = snapshot_annotations(database, case["id"], session)
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


def overwrite_draft(database: Database, case: dict, user: dict, target_id, session) -> dict:
    """整篇恢复：先原子保存当前正文与批注为新版本，再恢复目标稿及其批注。"""
    target, locked = _prepare_restore(database, case, user, target_id, session)
    baseline = create_version(
        database, locked, user, MANUAL_VERSION_KIND, RESTORE_BASELINE_TITLE,
        locked["document"], session,
    )
    restored = _restore_assets(database, locked, target, session)
    restore_draft_annotations(database, case["id"], target, session)
    _append_restore_record(database, restored, user, target, session)
    return {
        "case": internal_case_view(restored, user),
        "baselineVersionId": baseline["id"],
    }


def _prepare_restore(database, case, user, target_id, session):
    """覆盖前置校验：作者+工作稿+合法目标+并发锁。"""
    _require_draft_owner(case, user)
    if not target_id:
        raise CaseError(422, "恢复目标不能为空")
    target = _overwrite_target(database, case["id"], target_id, session)
    return target, _lock_case(database, case, user, session)


def _restore_assets(database, locked: dict, target: dict, session) -> dict:
    """恢复正文、附件、素材与来源；CAS 失败抛冲突由事务回滚。"""
    restored = _restore_case(database, locked, target, session)
    if not restored:
        raise CaseError(409, "案例状态已变化")
    _restore_attachments(database, locked["id"], target, session)
    restore_materials(database, locked["id"], target, session)
    restore_case_sources(database, locked["id"], target, session)
    return restored


def _append_restore_record(database, restored: dict, user: dict, target: dict, session):
    """恢复完成后追加一条 restore 记录；document 为恢复后的目标正文。"""
    record = create_version(
        database, restored, user, RESTORE_VERSION_KIND,
        f"恢复：{target['title']}", target["document"], session,
        restored_from_id=target["id"],
    )
    return record
