from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import get_database, get_settings
from app.modules.auth.dependencies import optional_user, require_csrf, require_user
from app.modules.case_sources.models import CaseSourceCreate, CaseSourceView
from app.modules.case_sources.service import (
    list_case_sources,
    mount_case_source,
    unmount_case_source,
)

router = APIRouter(prefix="/api/cases/{case_id}/case-sources", tags=["case-sources"])


@router.get("", response_model=list[CaseSourceView], response_model_exclude_none=True)
def index(
    case_id: str,
    request: Request,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    settings=Depends(get_settings),
    user: dict | None = Depends(optional_user),
):
    origin = settings.public_base_url or str(request.base_url).rstrip("/")
    return list_case_sources(database, case_id, user, version_id, origin)


@router.post(
    "", response_model=CaseSourceView, response_model_exclude_none=True, status_code=201
)
def create(
    case_id: str,
    body: CaseSourceCreate,
    request: Request,
    database=Depends(get_database),
    settings=Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    origin = settings.public_base_url or str(request.base_url).rstrip("/")
    return mount_case_source(
        database, case_id, body.sourceCaseId, body.versionId, body.revision, user, origin
    )


@router.delete("/{source_id}", status_code=204)
def remove(
    case_id: str,
    source_id: str,
    revision: Annotated[int, Query(ge=1)],
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    unmount_case_source(database, case_id, source_id, revision, user)
