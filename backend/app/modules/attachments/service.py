from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import PurePosixPath

from fastapi import UploadFile
from pymongo import ReturnDocument
from pymongo.database import Database

from app.modules.attachments.models import AccessLevel
from app.modules.attachments.storage import BlobStore
from app.modules.attachments.text import extract_search_text
from app.modules.cases.service import CaseError, RevisionConflict

MAX_ATTACHMENT_BYTES = 128 * 1024 * 1024
SNAPSHOT_FIELDS = (
    "id",
    "caseId",
    "name",
    "mediaType",
    "size",
    "accessLevel",
    "blobId",
    "searchText",
    "createdAt",
)


class AttachmentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _case(database: Database, case_id: str) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise AttachmentError(404, "案例不存在")
    return case


def _require_author_draft(case: dict, user: dict) -> None:
    if case["ownerId"] != user["id"]:
        raise AttachmentError(403, "仅案例作者可修改附件")
    if case["workflowStatus"] != "draft":
        raise AttachmentError(409, "案例当前不可编辑")


def _require_reader(case: dict, user: dict | None) -> None:
    is_reader = case["publicationStatus"] == "public" or bool(
        user and (user["role"] == "admin" or case["ownerId"] == user["id"])
    )
    if not is_reader:
        raise AttachmentError(404, "案例不存在")


def _filename(value: str | None) -> str:
    name = PurePosixPath((value or "attachment").replace("\\", "/")).name
    return name[:255] or "attachment"


def _require_file_size(upload: UploadFile) -> int:
    size = upload.size or 0
    if size > MAX_ATTACHMENT_BYTES:
        raise AttachmentError(413, "附件不能超过 128MiB")
    return size


def attachment_view(attachment: dict) -> dict:
    fields = ("id", "name", "mediaType", "size", "accessLevel", "createdAt")
    return {field: attachment[field] for field in fields}


def snapshot_attachments(database: Database, case_id: str, session) -> list[dict]:
    rows = database.attachments.find({"caseId": case_id}, session=session).sort(
        "createdAt", 1
    )
    return [{field: row[field] for field in SNAPSHOT_FIELDS} for row in rows]


def _new_attachment(case_id, upload, access_level) -> dict:
    return _attachment_record(
        case_id, upload, access_level, _require_file_size(upload), _search_text(upload)
    )


def create_attachment(
    database: Database,
    store: BlobStore,
    case_id: str,
    upload: UploadFile,
    access_level: AccessLevel,
    user: dict,
    revision: int,
) -> dict:
    case = _case(database, case_id)
    _require_author_draft(case, user)
    attachment = _new_attachment(case_id, upload, access_level)
    _persist_attachment(database, store, attachment, upload, user, revision)
    return attachment_view(attachment)


def _search_text(upload: UploadFile) -> str:
    try:
        return extract_search_text(upload)
    except Exception as error:
        raise AttachmentError(422, "附件文本无法解析") from error


def _persist_attachment(database, store, attachment, upload, user, revision) -> None:
    _put(store, attachment, upload)
    try:
        _run_transaction(
            database,
            lambda session: _insert(database, attachment, user, revision, session),
        )
    except (AttachmentError, CaseError):
        _remove_safely(store, attachment["blobId"])
        raise


def _put(store: BlobStore, attachment: dict, upload: UploadFile) -> None:
    try:
        store.put(
            attachment["blobId"],
            upload.file,
            attachment["size"],
            attachment["mediaType"],
        )
    except Exception:
        _remove_safely(store, attachment["blobId"])
        raise


def _remove_safely(store: BlobStore, blob_id: str) -> None:
    try:
        store.remove(blob_id)
    except Exception:
        pass


def _run_transaction(database: Database, callback):
    with database.client.start_session() as session:
        return session.with_transaction(callback)


def _insert(database, attachment: dict, user: dict, revision: int, session) -> None:
    _advance_revision(database, attachment["caseId"], user, revision, session)
    database.attachments.insert_one(attachment, session=session)


def _advance_revision(
    database, case_id: str, user: dict, revision: int, session
) -> None:
    query = {
        "id": case_id,
        "ownerId": user["id"],
        "workflowStatus": "draft",
        "revision": revision,
    }
    updated = database.cases.find_one_and_update(
        query,
        {"$set": {"updatedAt": _now()}, "$inc": {"revision": 1}},
        session=session,
        return_document=ReturnDocument.AFTER,
    )
    if updated:
        return
    _raise_mutation_conflict(database, case_id, user, session)


def _raise_mutation_conflict(database, case_id: str, user: dict, session) -> None:
    case = database.cases.find_one({"id": case_id}, session=session)
    if not case:
        raise AttachmentError(404, "案例不存在")
    _require_author_draft(case, user)
    raise RevisionConflict(case["revision"])


def _attachment_record(
    case_id: str,
    upload: UploadFile,
    access_level: AccessLevel,
    size: int,
    search_text: str,
) -> dict:
    return {
        "id": f"att-{secrets.token_hex(8)}",
        "caseId": case_id,
        "name": _filename(upload.filename),
        "mediaType": upload.content_type or "application/octet-stream",
        "size": size,
        "accessLevel": access_level,
        "blobId": secrets.token_hex(16),
        "searchText": search_text,
        "createdAt": _now(),
    }


def list_attachments(
    database: Database, case_id: str, user: dict | None, version_id: str | None
) -> list[dict]:
    case = _case(database, case_id)
    _require_reader(case, user)
    rows = _attachment_rows(database, case, user, version_id)
    return [attachment_view(row) for row in rows]


def _is_internal(case: dict, user: dict | None) -> bool:
    return bool(user and (user["role"] == "admin" or case["ownerId"] == user["id"]))


def _attachment_rows(database, case: dict, user: dict | None, version_id: str | None):
    if version_id:
        return _version_rows(database, case, user, version_id)
    if _is_internal(case, user):
        return list(
            database.attachments.find({"caseId": case["id"]}).sort("createdAt", 1)
        )
    return _version_rows(database, case, user, case.get("publishedVersionId"))


def _version_rows(database, case: dict, user: dict | None, version_id: str | None):
    if not version_id or (
        version_id != case.get("publishedVersionId") and not _is_internal(case, user)
    ):
        raise AttachmentError(404, "附件版本不存在")
    version = database.case_versions.find_one({"id": version_id, "caseId": case["id"]})
    version = version or database.case_snapshots.find_one(
        {"id": version_id, "caseId": case["id"]}
    )
    if not version:
        raise AttachmentError(404, "附件版本不存在")
    return version.get("attachments", [])


def download_attachment(
    database: Database,
    store: BlobStore,
    case_id: str,
    attachment_id: str,
    user: dict | None,
    version_id: str | None,
) -> tuple[dict, object]:
    case = _case(database, case_id)
    _require_reader(case, user)
    rows = _attachment_rows(database, case, user, version_id)
    attachment = next((row for row in rows if row["id"] == attachment_id), None)
    if not attachment:
        raise AttachmentError(404, "附件不存在")
    _require_content_access(case, attachment, user)
    return attachment, store.open(attachment["blobId"])


def _require_content_access(case: dict, attachment: dict, user: dict | None) -> None:
    internal = bool(user and (user["role"] == "admin" or case["ownerId"] == user["id"]))
    if internal or attachment["accessLevel"] == "public":
        return
    if attachment["accessLevel"] == "campus" and user:
        return
    raise AttachmentError(403, "无权读取该附件")


def delete_attachment(
    database: Database,
    store: BlobStore,
    case_id: str,
    attachment_id: str,
    user: dict,
    revision: int,
) -> None:
    _require_author_draft(_case(database, case_id), user)
    attachment, remove_blob = _run_transaction(
        database,
        lambda session: _delete(
            database, case_id, attachment_id, user, revision, session
        ),
    )
    if remove_blob:
        _remove_safely(store, attachment["blobId"])


def _delete(
    database, case_id: str, attachment_id: str, user: dict, revision: int, session
):
    query = {"id": attachment_id, "caseId": case_id}
    attachment = database.attachments.find_one(query, session=session)
    if not attachment:
        raise AttachmentError(404, "附件不存在")
    _advance_revision(database, case_id, user, revision, session)
    database.attachments.delete_one({"_id": attachment["_id"]}, session=session)
    query = {"attachments.blobId": attachment["blobId"]}
    referenced = database.case_versions.find_one(query, {"_id": 1}, session=session)
    referenced = referenced or database.case_snapshots.find_one(
        query, {"_id": 1}, session=session
    )
    return attachment, not referenced
