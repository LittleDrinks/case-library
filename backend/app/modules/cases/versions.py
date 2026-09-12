from __future__ import annotations

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


def next_version_number(database: Database, case_id: str, session) -> int:
    row = database.case_versions.find_one(
        {"caseId": case_id, "kind": {"$in": list(FORMAL_VERSION_KINDS)}},
        {"number": 1}, sort=[("number", DESCENDING)], session=session
    )
    return (row or {}).get("number", 0) + 1


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
    assets = (
        snapshot_attachments(database, case["id"], session),
        snapshot_materials(database, case["id"], session),
        snapshot_case_sources(database, case["id"], session),
    )
    return {
        "id": new_id("cv"), "caseId": case["id"],
        "number": next_version_number(database, case["id"], session),
        "kind": AI_VERSION_KIND, "title": case["title"],
        "summary": case.get("summary", ""), "document": document,
        "attachments": assets[0], "materials": assets[1], "caseSources": assets[2],
        "metadata": case_metadata(case), "sourceRevision": source_revision,
        "sourceRunId": run.id, "createdBy": run.user_id,
        "createdAt": datetime.now(UTC).isoformat(),
    }


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
    version = {
        "id": new_id("cv"), "caseId": case["id"],
        "number": next_version_number(database, case["id"], session),
        "kind": kind, "title": title,
        "summary": case.get("summary", ""), "document": document,
        "attachments": snapshot_attachments(database, case["id"], session),
        "materials": snapshot_materials(database, case["id"], session),
        "caseSources": snapshot_case_sources(database, case["id"], session),
        "metadata": case_metadata(case), "sourceRevision": case["revision"],
        "createdBy": user["id"],
        "createdAt": datetime.now(UTC).isoformat(),
    }
    if restored_from_id:
        version["restoredFromId"] = restored_from_id
    return version


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
