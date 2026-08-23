from __future__ import annotations

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.modules.attachments.service import _advance_revision, _run_transaction
from app.modules.cases.service import CaseError
from app.modules.materials.service import can_read_material
from app.modules.search.outbox import SearchOutbox

VIEW_FIELDS = (
    "id",
    "title",
    "summary",
    "source",
    "sourceUrl",
    "tags",
    "materialType",
    "authority",
    "accessLevel",
    "filename",
    "mediaType",
    "size",
)


def _case(database: Database, case_id: str) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise CaseError(404, "案例不存在")
    return case


def _require_reader(case: dict, user: dict | None) -> None:
    allowed = case["publicationStatus"] == "public" or bool(
        user and (user["role"] == "admin" or user["id"] == case["ownerId"])
    )
    if not allowed:
        raise CaseError(404, "案例不存在")


def material_view(row: dict) -> dict:
    details = {field: row[field] for field in VIEW_FIELDS if row.get(field) is not None}
    return {
        **details,
        "contentAvailable": True,
        "hasFile": bool(row.get("blobId") or row.get("hasFile")),
    }


def _restricted_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "accessLevel": row["accessLevel"],
        "contentAvailable": False,
        "hasFile": bool(row.get("blobId") or row.get("hasFile")),
    }


def snapshot_materials(database: Database, case_id: str, session) -> list[dict]:
    rows = database.case_materials.find({"caseId": case_id}, session=session).sort(
        "id", 1
    )
    return [material_view(row) for row in rows]


def list_case_materials(
    database: Database, case_id: str, user: dict | None, version_id: str | None
) -> list[dict]:
    case = _case(database, case_id)
    _require_reader(case, user)
    rows = _material_rows(database, case, user, version_id)
    if _is_internal(case, user):
        return [material_view(row) for row in rows]
    return [
        material_view(row) if can_read_material(row, user) else _restricted_view(row)
        for row in rows
    ]


def _is_internal(case: dict, user: dict | None) -> bool:
    return bool(user and (user["role"] == "admin" or user["id"] == case["ownerId"]))


def _material_rows(database, case: dict, user: dict | None, version_id: str | None):
    if not version_id and _is_internal(case, user):
        return snapshot_materials(database, case["id"], None)
    target_id = version_id or case.get("publishedVersionId")
    return _version_materials(database, case, user, target_id)


def _version_materials(database, case: dict, user: dict | None, version_id: str | None):
    if not version_id or (
        version_id != case.get("publishedVersionId") and not _is_internal(case, user)
    ):
        raise CaseError(404, "素材版本不存在")
    query = {"id": version_id, "caseId": case["id"]}
    version = database.case_versions.find_one(query)
    version = version or database.case_snapshots.find_one(query)
    if not version:
        raise CaseError(404, "素材版本不存在")
    return version.get("materials", [])


def _mounted(case_id: str, material: dict) -> dict:
    return {**material_view(material), "caseId": case_id, "materialId": material["id"]}


def _insert(database, case_id, material, revision, user, session) -> dict:
    _advance_revision(database, case_id, user, revision, session)
    mounted = _mounted(case_id, material)
    try:
        database.case_materials.insert_one(mounted, session=session)
    except DuplicateKeyError as error:
        raise CaseError(409, "素材已加入当前案例") from error
    _record_materials(database, [material["id"]], session)
    return material_view(mounted)


def _record_materials(database, material_ids, session, revoke=()) -> None:
    keys = [f"material:{material_id}" for material_id in dict.fromkeys(material_ids)]
    if keys:
        revoked = [f"material:{material_id}" for material_id in revoke]
        SearchOutbox(database).record(keys, revoke=revoked, session=session)


def mount_material(
    database: Database, case_id: str, material_id: str, revision: int, user: dict
) -> dict:
    material = database.materials.find_one({"id": material_id, "status": "active"})
    if not material or not can_read_material(material, user):
        raise CaseError(404, "素材不存在")
    return _run_transaction(
        database,
        lambda session: _insert(database, case_id, material, revision, user, session),
    )


def unmount_material(
    database: Database, case_id: str, material_id: str, revision: int, user: dict
) -> None:
    _run_transaction(
        database,
        lambda session: _delete(
            database, case_id, material_id, revision, user, session
        ),
    )


def _delete(database, case_id, material_id, revision, user, session) -> None:
    query = {"caseId": case_id, "materialId": material_id}
    mounted = database.case_materials.find_one(query, session=session)
    if not mounted:
        raise CaseError(404, "素材未加入当前案例")
    _advance_revision(database, case_id, user, revision, session)
    database.case_materials.delete_one({"_id": mounted["_id"]}, session=session)
    _record_materials(database, [material_id], session, [material_id])


def restore_materials(database, case_id: str, target: dict, session) -> None:
    previous = database.case_materials.distinct(
        "materialId",
        {"caseId": case_id},
        session=session,
    )
    database.case_materials.delete_many({"caseId": case_id}, session=session)
    rows = [_mounted(case_id, material) for material in target.get("materials", [])]
    if rows:
        database.case_materials.insert_many(rows, session=session)
    current = [row["materialId"] for row in rows]
    removed = set(previous) - set(current)
    _record_materials(database, previous + current, session, removed)
