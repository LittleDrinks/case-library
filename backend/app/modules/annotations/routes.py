from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import get_database
from app.modules.annotations.models import (
    AnnotationCreate,
    AnnotationPatch,
    AnnotationReplyCreate,
    AnnotationStatusPatch,
    AnnotationView,
)
from app.modules.annotations.service import (
    add_reply,
    change_status,
    create_annotation,
    delete_annotation,
    list_annotations,
    update_annotation,
)
from app.modules.auth.dependencies import require_csrf, require_user

router = APIRouter(prefix="/api/cases/{case_id}/annotations", tags=["annotations"])


@router.post(
    "", response_model=AnnotationView, response_model_exclude_none=True, status_code=201
)
def create(
    case_id: str,
    body: AnnotationCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return create_annotation(database, case_id, body.model_dump(by_alias=True, exclude_none=True), user)


@router.get("", response_model=list[AnnotationView], response_model_exclude_none=True)
def index(
    case_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
):
    return list_annotations(database, case_id, user)


@router.patch(
    "/{annotation_id}", response_model=AnnotationView, response_model_exclude_none=True
)
def edit(
    case_id: str,
    annotation_id: str,
    body: AnnotationPatch,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return update_annotation(database, case_id, annotation_id, body.content, user)


@router.delete("/{annotation_id}", status_code=204)
def remove(
    case_id: str,
    annotation_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    delete_annotation(database, case_id, annotation_id, user)
    return Response(status_code=204)


@router.post(
    "/{annotation_id}/replies", response_model=AnnotationView, response_model_exclude_none=True
)
def reply(
    case_id: str,
    annotation_id: str,
    body: AnnotationReplyCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return add_reply(database, case_id, annotation_id, body.content, user)


@router.patch(
    "/{annotation_id}/status", response_model=AnnotationView, response_model_exclude_none=True
)
def status(
    case_id: str,
    annotation_id: str,
    body: AnnotationStatusPatch,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return change_status(database, case_id, annotation_id, body.status, user)
