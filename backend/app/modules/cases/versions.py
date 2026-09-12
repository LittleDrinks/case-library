from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from pymongo import DESCENDING, ReturnDocument
from pymongo.database import Database
from app.core.ids import new_id
from app.modules.attachments.service import snapshot_attachments
from app.modules.case_materials.service import snapshot_materials
from app.modules.case_sources.service import snapshot_case_sources
from app.modules.cases.service import (
    CaseError,
    RevisionConflict,
    case_metadata,
    run_transaction,
)

AI_VERSION_KIND = "ai"
MANUAL_VERSION_KIND = "manual"
RESTORE_VERSION_KIND = "restore"
FORMAL_VERSION_KINDS = (
    "submission", AI_VERSION_KIND, MANUAL_VERSION_KIND, RESTORE_VERSION_KIND,
)
RESTORED_ANNOTATION_FIELDS = (
    "quote", "section", "content", "source", "from", "to", "quoteHash",
    "revision", "status", "replies", "revisions", "anchorState",
)


def next_version_number(database: Database, case_id: str, session) -> int:
    row = database.case_versions.find_one(
        {"caseId": case_id, "kind": {"$in": list(FORMAL_VERSION_KINDS)}},
        {"number": 1}, sort=[("number", DESCENDING)], session=session
    )
    return (row or {}).get("number", 0) + 1


def snapshot_annotations(database, case_id: str, session=None) -> list[dict]:
    rows = database.annotations.find(
        {"caseId": case_id, "versionId": None}, session=session,
    )
    return [_snapshot_copy(row) for row in rows]


def _snapshot_copy(row: dict) -> dict:
    snapshot = deepcopy(row)
    snapshot.pop("_id", None)
    return snapshot


def restore_draft_annotations(
    database: Database, case_id: str, target: dict, session,
) -> None:
    database.annotations.delete_many(
        {"caseId": case_id, "versionId": None}, session=session,
    )
    snapshots = list(target.get("annotations", []))
    if target["kind"] == "submission":
        rows = database.annotations.find(
            {"caseId": case_id, "versionId": target["id"],
             "source": {"$in": ["admin", "ai"]}}, session=session,
        )
        snapshots.extend(rows)
    restored = [_restore_annotation(row, case_id) for row in snapshots]
    if restored:
        database.annotations.insert_many(restored, session=session)


def _restore_annotation(row: dict, case_id: str) -> dict:
    restored = {
        "id": new_id("an"), "caseId": case_id, "versionId": None,
        "restoredFromId": row["id"], "createdBy": row["createdBy"],
        "createdAt": datetime.now(UTC).isoformat(),
    }
    for field in RESTORED_ANNOTATION_FIELDS:
        if row.get(field) is not None:
            restored[field] = deepcopy(row[field])
    return restored


def create_ai_version(database: Database, artifact, run, document: dict, session) -> dict | None:
    existing = _existing(database, artifact.case_id, run.id, session)
    if existing:
        return existing
    case = database.cases.find_one({"id": artifact.case_id}, session=session)
    if not _eligible(case, artifact, run):
        return None
    return _insert(database, case, run, document, case["revision"], session)


def create_ai_version_from_write(database: Database, write: dict, run, session) -> dict | None:
    if write.get("scope") != "document":
        return None
    existing = _existing(database, write["caseId"], run.id, session)
    if existing:
        return existing
    case = database.cases.find_one({"id": write["caseId"]}, session=session)
    if not _write_eligible(case, write, run):
        return None
    return _insert(database, case, run, write["document"], write["resultRevision"], session)


def _existing(database: Database, case_id: str, run_id: str, session) -> dict | None:
    return database.case_versions.find_one(
        {"caseId": case_id, "kind": AI_VERSION_KIND, "sourceRunId": run_id},
        session=session,
    )


def _eligible(case: dict | None, artifact, run) -> bool:
    return bool(
        case and not run.read_only and artifact.run_id == run.id
        and artifact.thread_id == run.thread_id and case.get("ownerId") == run.user_id
        and case.get("workflowStatus") == "draft"
        and case.get("revision") == run.base_revision
    )


def _write_eligible(case: dict | None, write: dict, run) -> bool:
    return bool(
        case and write.get("status") in ("written", "undone")
        and write.get("runId") == run.id and write.get("threadId") == run.thread_id
        and write.get("baseRevision") == run.base_revision and not run.read_only
        and case.get("ownerId") == run.user_id and case.get("workflowStatus") == "draft"
    )


def _insert(database, case: dict, run, document: dict, source_revision: int, session) -> dict:
    version = _record(database, case, run, document, source_revision, session)
    database.case_versions.insert_one(version, session=session)
    return version


def _record(database, case: dict, run, document: dict, source_revision: int, session) -> dict:
    version = _version_record_base(
        database, case, AI_VERSION_KIND, case["title"], document,
        source_revision, run.user_id, session,
    )
    version["sourceRunId"] = run.id
    return version


def create_version(
    database: Database, case: dict, user: dict, kind: str, title: str,
    document: dict, session, restored_from_id: str | None = None,
) -> dict:
    """在既有事务内以指定 kind 冻结当前三源快照并插入一条正式版本。"""
    version = _version_record(
        database, case, user, kind, title, document, session, restored_from_id,
    )
    database.case_versions.insert_one(version, session=session)
    return {key: value for key, value in version.items() if key != "_id"}


def _version_record(
    database, case, user, kind, title, document, session, restored_from_id,
) -> dict:
    version = _version_record_base(
        database, case, kind, title, document, case["revision"], user["id"], session,
    )
    if restored_from_id:
        version["restoredFromId"] = restored_from_id
    return version


def _version_assets(database, case_id: str, session) -> tuple[list, list, list]:
    return (
        snapshot_attachments(database, case_id, session),
        snapshot_materials(database, case_id, session),
        snapshot_case_sources(database, case_id, session),
    )


def _version_record_base(
    database, case, kind, title, document, source_revision, created_by, session,
) -> dict:
    attachments, materials, case_sources = _version_assets(database, case["id"], session)
    return {
        "id": new_id("cv"), "caseId": case["id"],
        "number": next_version_number(database, case["id"], session), "kind": kind,
        "title": title, "summary": case.get("summary", ""), "document": document,
        "attachments": attachments, "materials": materials, "caseSources": case_sources,
        "annotations": snapshot_annotations(database, case["id"], session),
        "metadata": case_metadata(case), "sourceRevision": source_revision,
        "createdBy": created_by, "createdAt": datetime.now(UTC).isoformat(),
    }


def create_manual_version(
    database: Database, case_id: str, title: str, user: dict, revision: int,
) -> dict:
    """手动命名版本：CAS 校验作者与工作稿后原子冻结当前正文与三源。"""

    def _create(session):
        case = _manual_case(database, case_id, user, revision, session)
        version = create_version(
            database, case, user, MANUAL_VERSION_KIND, title, case["document"], session,
        )
        _touch_manual_case(database, case_id, revision, session)
        return version

    return run_transaction(database, _create)


def _touch_manual_case(database, case_id: str, revision: int, session) -> None:
    updated = database.cases.find_one_and_update(
        {"id": case_id, "revision": revision},
        {"$set": {"updatedAt": datetime.now(UTC).isoformat()}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER, session=session,
    )
    if not updated:
        raise RevisionConflict(revision)


def _manual_case(database, case_id, user, revision: int, session) -> dict:
    case = database.cases.find_one(
        {"id": case_id, "ownerId": user["id"], "workflowStatus": "draft",
         "revision": revision},
        session=session,
    )
    if not case:
        _reject_manual_version(database, case_id, user, session)
    return case


def _reject_manual_version(database, case_id: str, user: dict, session) -> None:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise CaseError(404, "案例不存在")
    if case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可创建版本")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "仅工作版本可创建版本")
    raise RevisionConflict(case["revision"])
