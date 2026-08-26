from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from pathlib import PurePath, PurePosixPath

from fastapi import UploadFile
from pymongo import ReturnDocument
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.modules.attachments.storage import BlobStore
from app.modules.materials.archive import PreparedFile, prepare_files
from app.modules.materials.errors import MaterialImportError
from app.modules.materials.models import AccessLevel
from app.modules.materials.models import CandidateDecision
from app.modules.search.outbox import SearchOutbox

MATERIAL_DETAIL_FIELDS = (
    "id", "title", "summary", "excerpt", "source", "sourceUrl", "tags",
    "publishedAt", "collectedAt", "createdAt", "updatedAt", "materialType",
    "authority", "accessLevel", "citedCount", "lastCitedAt", "filename",
    "mediaType", "size",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _digest(source) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        digest.update(chunk)
    source.seek(0)
    return digest.hexdigest()


def _candidate(file: PreparedFile, digest: str, access: str, user: dict) -> dict:
    return {
        "id": _id("mc"),
        "filename": file.filename,
        "mediaType": file.media_type,
        "size": file.size,
        "sha256": digest,
        "blobId": digest,
        "accessLevel": access,
        "status": "candidate",
        "createdBy": user["id"],
        "createdAt": _now(),
    }


def _queued_item(job: dict, file: PreparedFile, order: int) -> dict:
    return {
        "id": _id("mi"),
        "jobId": job["id"],
        "order": order,
        "filename": file.filename,
        "status": "queued",
        "mediaType": file.media_type,
        "size": file.size,
    }


def _persist_candidate(database, store, source, file, digest, access, user):
    existing = database.material_candidates.find_one({"sha256": digest})
    if existing:
        return existing, True
    candidate = _candidate(file, digest, access, user)
    store.put(digest, source, file.size, file.media_type)
    try:
        database.material_candidates.insert_one(candidate)
        return candidate, False
    except DuplicateKeyError:
        return database.material_candidates.find_one({"sha256": digest}), True


def _finish_item(database, item_id: str, digest: str, candidate: dict, duplicate: bool):
    outcome = {"status": "duplicate", "duplicateOf": candidate["id"]}
    if not duplicate:
        outcome = {"status": "candidate", "candidateId": candidate["id"]}
    database.material_import_items.update_one(
        {"id": item_id}, {"$set": {"sha256": digest, **outcome}}
    )


def _fail_item(database, item_id: str, detail: str) -> None:
    database.material_import_items.update_one(
        {"id": item_id}, {"$set": {"status": "failed", "error": detail[:500]}}
    )


def _process_file(database, store, file, item, access, user) -> None:
    if file.error or not file.path:
        _fail_item(database, item["id"], file.error or "文件不可读")
        return
    database.material_import_items.update_one(
        {"id": item["id"]}, {"$set": {"status": "running"}}
    )
    with file.path.open("rb") as source:
        digest = _digest(source)
        candidate, duplicate = _persist_candidate(
            database, store, source, file, digest, access, user
        )
    _finish_item(database, item["id"], digest, candidate, duplicate)


def _process_safely(database, store, file, item, access, user) -> None:
    try:
        _process_file(database, store, file, item, access, user)
    except Exception:
        _fail_item(database, item["id"], "文件处理失败")


def _job(database, access: str, user: dict, item_count: int) -> dict:
    job = {
        "id": _id("mj"),
        "status": "running",
        "accessLevel": access,
        "itemCount": item_count,
        "createdBy": user["id"],
        "createdAt": _now(),
        "completedAt": None,
    }
    database.material_import_jobs.insert_one(job)
    return job


def _job_status(statuses: list[str]) -> str:
    succeeded = any(status in {"candidate", "duplicate"} for status in statuses)
    failed = any(status == "failed" for status in statuses)
    if succeeded and failed:
        return "partial_success"
    return "succeeded" if succeeded else "failed"


def _finish_job(database, job_id: str) -> None:
    rows = database.material_import_items.find({"jobId": job_id}, {"status": 1})
    status = _job_status([row["status"] for row in rows])
    database.material_import_jobs.update_one(
        {"id": job_id}, {"$set": {"status": status, "completedAt": _now()}}
    )


def create_import(
    database: Database,
    store: BlobStore,
    uploads: list[UploadFile],
    access: AccessLevel,
    user: dict,
) -> dict:
    with prepare_files(uploads) as files:
        job = _job(database, access, user, len(files))
        for order, file in enumerate(files):
            item = _queued_item(job, file, order)
            database.material_import_items.insert_one(item)
            _process_safely(database, store, file, item, access, user)
        _finish_job(database, job["id"])
        return get_import(database, job["id"])


def _clean(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "_id"}


def can_read_material(material: dict, user: dict | None) -> bool:
    if material.get("accessLevel") == "public":
        return True
    if material.get("accessLevel") == "campus":
        return bool(user)
    return bool(
        user and (user["role"] == "admin" or material.get("createdBy") == user["id"])
    )


def _readable_material(database, material_id: str, user: dict | None) -> dict:
    material = database.materials.find_one({"id": material_id, "status": "active"})
    if not material or not can_read_material(material, user):
        raise MaterialImportError(404, "素材不存在")
    return material


def _detail_view(material: dict) -> dict:
    view = {key: material.get(key) for key in MATERIAL_DETAIL_FIELDS}
    view.update({"hasFile": bool(material.get("blobId")), "contentAvailable": True})
    view["downloadAvailable"] = view["hasFile"]
    return view


def get_material_detail(database, material_id: str, user: dict | None) -> dict:
    return _detail_view(_readable_material(database, material_id, user))


def download_material(database, store, material_id: str, user: dict | None):
    material = _readable_material(database, material_id, user)
    if not material.get("blobId"):
        raise MaterialImportError(404, "素材不存在")
    return material, store.open(material["blobId"])


def material_filename(material: dict) -> str:
    value = str(material.get("filename") or "material").replace("\\", "/")
    return PurePosixPath(value).name[:255] or "material"


def get_import(database: Database, job_id: str) -> dict | None:
    job = database.material_import_jobs.find_one({"id": job_id})
    if not job:
        return None
    rows = database.material_import_items.find({"jobId": job_id}).sort("order", 1)
    return {**_clean(job), "items": [_clean(row) for row in rows]}


def list_candidates(database: Database, status: str, page: int, page_size: int) -> dict:
    query = {"status": status}
    offset = (page - 1) * page_size
    rows = database.material_candidates.find(query).sort(
        [
            ("createdAt", -1),
            ("id", -1),
        ]
    )
    items = [_clean(row) for row in rows.skip(offset).limit(page_size)]
    return {
        "page": page,
        "pageSize": page_size,
        "total": database.material_candidates.count_documents(query),
        "items": items,
    }


def _metadata(body: CandidateDecision) -> dict:
    fields = ("summary", "source", "sourceUrl", "tags", "materialType", "authority")
    values = body.model_dump(include=set(fields), exclude_none=True)
    return {key: value for key, value in values.items() if value != ""}


def _title(candidate: dict, body: CandidateDecision) -> str:
    if body.title:
        return body.title.strip()
    return PurePath(candidate["filename"]).stem[:300] or candidate["filename"][:300]


def _material(candidate: dict, body: CandidateDecision, user: dict) -> dict:
    fields = ("blobId", "sha256", "filename", "mediaType", "size", "accessLevel")
    return {
        "id": candidate["id"],
        "title": _title(candidate, body),
        **{field: candidate[field] for field in fields},
        **_metadata(body),
        "status": "active",
        "createdBy": candidate["createdBy"],
        "createdAt": candidate["createdAt"],
        "publishedAt": _now(),
        "approvedBy": user["id"],
        "publicReferenceCount": 0,
        "provenance": {"candidateId": candidate["id"]},
    }


def _decision_update(body: CandidateDecision, user: dict) -> dict:
    status = "approved" if body.decision == "approve" else "rejected"
    return {"status": status, "decidedAt": _now(), "decidedBy": user["id"]}


def _decide(database, candidate_id, body, user, session) -> dict:
    candidate = database.material_candidates.find_one(
        {"id": candidate_id}, session=session
    )
    if not candidate:
        raise MaterialImportError(404, "候选素材不存在")
    if candidate["status"] != "candidate":
        raise MaterialImportError(409, "候选素材已经审核")
    update = _decision_update(body, user)
    if body.decision == "approve":
        database.materials.insert_one(_material(candidate, body, user), session=session)
        SearchOutbox(database).record([f"material:{candidate_id}"], session=session)
        update["materialId"] = candidate_id
    return database.material_candidates.find_one_and_update(
        {"id": candidate_id, "status": "candidate"},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
        session=session,
    )


def _transaction(database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(lambda active: callback(active))


def decide_candidate(
    database: Database, candidate_id: str, body: CandidateDecision, user: dict
) -> dict:
    try:
        result = _transaction(
            database,
            lambda session: _decide(database, candidate_id, body, user, session),
        )
    except DuplicateKeyError as error:
        raise MaterialImportError(409, "候选素材已经审核") from error
    if not result:
        raise MaterialImportError(409, "候选素材已经审核")
    return _clean(result)
