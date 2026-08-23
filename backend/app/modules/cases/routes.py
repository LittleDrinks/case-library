from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import get_database
from app.modules.auth.dependencies import optional_user, require_csrf, require_user
from app.modules.cases.lifecycle import execute_lifecycle, get_history
from app.modules.cases.models import CaseCreate, CasePatch, LifecycleCommand
from app.modules.cases.service import (
    create_case,
    get_case,
    get_public_case,
    list_cases,
    update_case,
)
from app.modules.documents import build_case_docx

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("")
def index(
    scope: Literal["public", "mine", "admin"],
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    return list_cases(database, user, scope)


@router.post("")
def create(
    body: CaseCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return create_case(database, body.model_dump(), user)


@router.get("/{case_id}")
def detail(
    case_id: str,
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    return get_case(database, case_id, user)


@router.get("/{case_id}/public")
def public_detail(case_id: str, database=Depends(get_database)):
    return get_public_case(database, case_id)


@router.get("/{case_id}/public/export.docx")
def export_public_docx(case_id: str, database=Depends(get_database)):
    return _docx_response(get_public_case(database, case_id), case_id)


@router.get("/{case_id}/export.docx")
def export_docx(
    case_id: str,
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    return _docx_response(get_case(database, case_id, user), case_id)


def _docx_response(case: dict, case_id: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="case-{case_id}.docx"'}
    return Response(
        build_case_docx(case),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@router.patch("/{case_id}")
def save(
    case_id: str,
    body: CasePatch,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return update_case(database, case_id, body.model_dump(), user)


@router.post("/{case_id}/lifecycle")
def lifecycle(
    case_id: str,
    body: LifecycleCommand,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return execute_lifecycle(database, case_id, body.model_dump(), user)


@router.get("/{case_id}/history")
def history(
    case_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
):
    return get_history(database, case_id, user)
