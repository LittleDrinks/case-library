from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_blob_store, get_database
from app.modules.auth.dependencies import optional_user, require_csrf, require_user
from app.modules.materials.models import (
    AccessLevel,
    CandidateDecision,
    MaterialCandidatePage,
    MaterialCandidateView,
    MaterialImportJobView,
)
from app.modules.materials.service import (
    create_import,
    decide_candidate,
    download_material,
    get_import,
    list_candidates,
    material_filename,
)

router = APIRouter(prefix="/api/admin/material-imports", tags=["materials"])
candidate_router = APIRouter(
    prefix="/api/admin/material-candidates", tags=["materials"]
)
content_router = APIRouter(prefix="/api/materials", tags=["materials"])


def _admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可批量导入素材")
    return user


@router.post("", response_model=MaterialImportJobView, status_code=201)
def create(
    files: Annotated[list[UploadFile], File()],
    access_level: Annotated[AccessLevel, Form(alias="accessLevel")] = "campus",
    database=Depends(get_database),
    store=Depends(get_blob_store),
    user: dict = Depends(_admin),
    _session: dict = Depends(require_csrf),
):
    return create_import(database, store, files, access_level, user)


@router.get("/{job_id}", response_model=MaterialImportJobView)
def show(
    job_id: str,
    database=Depends(get_database),
    _user: dict = Depends(_admin),
):
    job = get_import(database, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="批量导入任务不存在")
    return job


@candidate_router.get(
    "",
    response_model=MaterialCandidatePage,
    response_model_exclude_none=True,
)
def candidates(
    status: Literal["candidate", "approved", "rejected"] = "candidate",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=50),
    database=Depends(get_database),
    _user: dict = Depends(_admin),
):
    return list_candidates(database, status, page, page_size)


@candidate_router.post(
    "/{candidate_id}/decision",
    response_model=MaterialCandidateView,
    response_model_exclude_none=True,
)
def decide(
    candidate_id: str,
    body: CandidateDecision,
    database=Depends(get_database),
    user: dict = Depends(_admin),
    _session: dict = Depends(require_csrf),
):
    return decide_candidate(database, candidate_id, body, user)


@content_router.get("/{material_id}/content")
def content(
    material_id: str,
    database=Depends(get_database),
    store=Depends(get_blob_store),
    user: dict | None = Depends(optional_user),
):
    material, chunks = download_material(database, store, material_id, user)
    filename = quote(material_filename(material), safe="")
    return StreamingResponse(
        chunks,
        media_type=material["mediaType"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
