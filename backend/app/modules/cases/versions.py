from __future__ import annotations

from datetime import UTC, datetime

from pymongo import DESCENDING
from pymongo.database import Database

from app.core.ids import new_id
from app.modules.attachments.service import snapshot_attachments
from app.modules.case_materials.service import snapshot_materials
from app.modules.case_sources.service import snapshot_case_sources
from app.modules.cases.service import case_metadata

AI_VERSION_KIND = "ai"
FORMAL_VERSION_KINDS = ("submission", AI_VERSION_KIND)


def next_version_number(database: Database, case_id: str, session) -> int:
    row = database.case_versions.find_one(
        {"caseId": case_id, "kind": {"$in": list(FORMAL_VERSION_KINDS)}},
        {"number": 1}, sort=[("number", DESCENDING)], session=session
    )
    return (row or {}).get("number", 0) + 1


def create_ai_version(database: Database, artifact, run, document: dict, session) -> dict | None:
    existing = database.case_versions.find_one(
        {"caseId": artifact.case_id, "kind": AI_VERSION_KIND, "sourceRunId": run.id},
        session=session,
    )
    if existing:
        return existing
    case = database.cases.find_one({"id": artifact.case_id}, session=session)
    if not _eligible(case, artifact, run):
        return None
    version = _record(database, case, artifact, run, document, session)
    database.case_versions.insert_one(version, session=session)
    return version


def _eligible(case: dict | None, artifact, run) -> bool:
    return bool(
        case and not run.read_only and artifact.run_id == run.id
        and artifact.thread_id == run.thread_id and case.get("ownerId") == run.user_id
        and case.get("workflowStatus") == "draft"
        and case.get("revision") == run.base_revision
    )


def _record(database, case: dict, artifact, run, document: dict, session) -> dict:
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
        "metadata": case_metadata(case), "sourceRevision": case["revision"],
        "sourceRunId": run.id, "createdBy": run.user_id,
        "createdAt": datetime.now(UTC).isoformat(),
    }
