from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_blob_store, get_database
from app.modules.attachments.models import AccessLevel, AttachmentView
from app.modules.attachments.service import (
    attachment_content_readable,
    create_attachment,
    delete_attachment,
    download_attachment,
    list_attachments,
)
from app.modules.attachments.storage import access_checked_chunks
from app.modules.auth.dependencies import optional_user, require_csrf, require_user
from app.modules.auth.sessions import load_current_user

router = APIRouter(prefix="/api/cases/{case_id}/attachments", tags=["attachments"])


@router.post("", response_model=AttachmentView, status_code=201)
def upload(
    case_id: str,
    file: Annotated[UploadFile, File()],
    access_level: Annotated[AccessLevel, Form(alias="accessLevel")],
    revision: Annotated[int, Form(ge=1)],
    database=Depends(get_database),
    store=Depends(get_blob_store),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return create_attachment(
        database, store, case_id, file, access_level, user, revision
    )


@router.get("", response_model=list[AttachmentView])
def index(
    case_id: str,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    return list_attachments(database, case_id, user, version_id)


@router.get("/{attachment_id}/content")
def content(
    case_id: str,
    attachment_id: str,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    store=Depends(get_blob_store),
    user: dict | None = Depends(optional_user),
):
    attachment, chunks = download_attachment(
        database, store, case_id, attachment_id, user, version_id
    )

    def can_read_current_attachment() -> bool:
        current_user = load_current_user(database, user)
        return attachment_content_readable(
            database,
            case_id,
            attachment_id,
            current_user,
            version_id,
            attachment["blobId"],
        )

    disposition = f"attachment; filename*=UTF-8''{quote(attachment['name'])}"
    return StreamingResponse(
        access_checked_chunks(chunks, can_read_current_attachment),
        media_type=attachment["mediaType"],
        headers={"Content-Disposition": disposition},
    )


@router.delete("/{attachment_id}", status_code=204)
def remove(
    case_id: str,
    attachment_id: str,
    revision: Annotated[int, Query(ge=1)],
    database=Depends(get_database),
    store=Depends(get_blob_store),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    delete_attachment(database, store, case_id, attachment_id, user, revision)
