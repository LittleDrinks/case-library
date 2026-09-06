from __future__ import annotations

import secrets
from datetime import UTC, datetime

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.modules.attachments.service import _advance_revision, _run_transaction
from app.modules.cases.published import version_readable
from app.modules.cases.service import CaseError
from app.modules.cases.sources import source_case_content_available, source_case_url

STORAGE_FIELDS = (
    "id",
    "sourceType",
    "caseId",
    "sourceCaseId",
    "versionId",
    "versionNumber",
    "title",
    "contentAvailable",
    "createdAt",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _case(database: Database, case_id: str) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "案例不存在")
    return case


def embed_row(row: dict) -> dict:
    return {field: row[field] for field in STORAGE_FIELDS if field in row}


def _source_case_info(database: Database, source_case_id: str) -> dict:
    source = database.cases.find_one(
        {"id": source_case_id}, {"publicationStatus": 1, "ownerId": 1, "publishedAt": 1}
    )
    return source or {}


def source_view(
    database: Database, row: dict, user: dict | None, origin: str
) -> dict:
    source = _source_case_info(database, row["sourceCaseId"])
    return {
        "id": row["id"],
        "sourceType": "case",
        "caseId": row["sourceCaseId"],
        "versionId": row["versionId"],
        "versionNumber": row["versionNumber"],
        "title": row["title"],
        "sourceUrl": source_case_url(origin, row["sourceCaseId"], row["versionId"]),
        "publishedAt": source.get("publishedAt"),
        "contentAvailable": source_case_content_available(
            database, row["sourceCaseId"], user
        ),
        "createdAt": row["createdAt"],
    }


def _draft_case(database: Database, case_id: str, user: dict) -> dict:
    case = _case(database, case_id)
    if case["ownerId"] != user["id"]:
        raise CaseError(403, "仅案例作者可管理案例来源")
    if case["workflowStatus"] != "draft":
        raise CaseError(409, "案例当前不可编辑")
    return case


def _pinned_version(
    database: Database, source_case: dict, version_id: str | None
) -> dict:
    if source_case.get("publicationStatus") != "public":
        raise CaseError(409, "案例来源必须固定到已发布版本")
    if not version_id:
        version_id = source_case.get("publishedVersionId")
    if not version_id:
        raise CaseError(409, "案例来源必须固定到已发布版本")
    version = database.case_versions.find_one(
        {"id": version_id, "caseId": source_case["id"]}
    )
    if not version_readable(database, source_case, version_id, version, False):
        raise CaseError(404, "案例版本不存在")
    return version


def _mounted(case_id: str, source_case: dict, version: dict) -> dict:
    return {
        "id": f"src-{secrets.token_hex(8)}",
        "sourceType": "case",
        "caseId": case_id,
        "sourceCaseId": source_case["id"],
        "versionId": version["id"],
        "versionNumber": version["number"],
        "title": version["title"],
        "contentAvailable": True,
        "createdAt": _now(),
    }


def _insert(database, case_id, source_case, version, user, revision, session) -> dict:
    _advance_revision(database, case_id, user, revision, session)
    mounted = _mounted(case_id, source_case, version)
    try:
        database.case_sources.insert_one(mounted, session=session)
    except DuplicateKeyError as error:
        raise CaseError(409, "案例来源已加入当前案例") from error
    return mounted


def _mount_inputs(
    database: Database, case_id: str, source_case_id: str, user: dict
) -> tuple[dict, dict]:
    _draft_case(database, case_id, user)
    if source_case_id == case_id:
        raise CaseError(409, "不能引用当前案例")
    source_case = database.cases.find_one({"id": source_case_id})
    if not source_case:
        raise CaseError(404, "案例不存在")
    return _case(database, case_id), source_case


def mount_case_source(
    database: Database,
    case_id: str,
    source_case_id: str,
    version_id: str | None,
    revision: int,
    user: dict,
    origin: str,
) -> dict:
    case, source_case = _mount_inputs(database, case_id, source_case_id, user)
    version = _pinned_version(database, source_case, version_id)
    mounted = _run_transaction(
        database,
        lambda session: _insert(
            database, case["id"], source_case, version, user, revision, session
        ),
    )
    return source_view(database, mounted, user, origin)


def list_case_sources(
    database: Database,
    case_id: str,
    user: dict | None,
    version_id: str | None,
    origin: str,
) -> list[dict]:
    case = _case(database, case_id)
    _require_source_reader(case, user)
    rows = _source_rows(database, case, user, version_id)
    return [source_view(database, row, user, origin) for row in rows]


def _require_source_reader(case: dict, user: dict | None) -> None:
    allowed = case["publicationStatus"] == "public" or bool(
        user and (user["role"] == "admin" or user["id"] == case["ownerId"])
    )
    if not allowed:
        raise CaseError(404, "案例不存在")


def _is_internal(case: dict, user: dict | None) -> bool:
    return bool(user and (user["role"] == "admin" or user["id"] == case["ownerId"]))


def _source_rows(database, case: dict, user: dict | None, version_id: str | None):
    if not version_id and _is_internal(case, user):
        return _live_rows(database, case["id"])
    target_id = version_id or case.get("publishedVersionId")
    return _version_rows(database, case, user, target_id)


def _live_rows(database: Database, case_id: str) -> list[dict]:
    return list(database.case_sources.find({"caseId": case_id}).sort("id", 1))


def _version_rows(database, case: dict, user: dict | None, version_id: str | None):
    internal = _is_internal(case, user)
    if not version_id:
        raise CaseError(404, "案例来源版本不存在")
    query = {"id": version_id, "caseId": case["id"]}
    version = database.case_versions.find_one(query)
    version = version or database.case_snapshots.find_one(query)
    if not version or not version_readable(database, case, version_id, version, internal):
        raise CaseError(404, "案例来源版本不存在")
    return version.get("caseSources", [])


def _delete(database, case_id, source_id, user, revision, session) -> None:
    from app.modules.cases.sources import require_uncited

    query = {"caseId": case_id, "id": source_id}
    mounted = database.case_sources.find_one(query, session=session)
    if not mounted:
        raise CaseError(404, "案例来源未加入当前案例")
    require_uncited(database, case_id, "case", source_id, session)
    _advance_revision(database, case_id, user, revision, session)
    database.case_sources.delete_one({"_id": mounted["_id"]}, session=session)


def unmount_case_source(
    database: Database, case_id: str, source_id: str, revision: int, user: dict
) -> None:
    _draft_case(database, case_id, user)
    _run_transaction(
        database,
        lambda session: _delete(database, case_id, source_id, user, revision, session),
    )


def snapshot_case_sources(database: Database, case_id: str, session) -> list[dict]:
    rows = database.case_sources.find({"caseId": case_id}, session=session).sort("id", 1)
    return [embed_row(row) for row in rows]


def restore_case_sources(database, case_id: str, target: dict, session) -> None:
    database.case_sources.delete_many({"caseId": case_id}, session=session)
    rows = [{**row, "caseId": case_id} for row in target.get("caseSources", [])]
    if rows:
        database.case_sources.insert_many(rows, session=session)
