from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_database
from app.modules.annotations.models import (
    AnnotationCreate,
    AnnotationReplyCreate,
    AnnotationStatusPatch,
    AnnotationView,
)
from app.modules.annotations.service import (
    add_reply,
    change_status,
    create_annotation,
    list_annotations,
)
from app.modules.auth.dependencies import require_csrf, require_user

router = APIRouter(prefix="/api/cases/{case_id}/annotations", tags=["annotations"])


@router.post("", response_model=AnnotationView, status_code=201)
def create(
    case_id: str,
    body: AnnotationCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return create_annotation(database, case_id, body.model_dump(), user)


@router.get("", response_model=list[AnnotationView])
def index(
    case_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
):
    return list_annotations(database, case_id, user)


@router.post("/{annotation_id}/replies", response_model=AnnotationView)
def reply(
    case_id: str,
    annotation_id: str,
    body: AnnotationReplyCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return add_reply(database, case_id, annotation_id, body.content, user)


@router.patch("/{annotation_id}/status", response_model=AnnotationView)
def status(
    case_id: str,
    annotation_id: str,
    body: AnnotationStatusPatch,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return change_status(database, case_id, annotation_id, body.status, user)
