from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.dependencies import get_database
from app.modules.auth.dependencies import optional_user, require_csrf, require_user
from app.modules.case_materials.models import CaseMaterialCreate, CaseMaterialView
from app.modules.case_materials.service import (
    list_case_materials,
    mount_material,
    unmount_material,
)

router = APIRouter(prefix="/api/cases/{case_id}/materials", tags=["case-materials"])


@router.get("", response_model=list[CaseMaterialView], response_model_exclude_none=True)
def index(
    case_id: str,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    return list_case_materials(database, case_id, user, version_id)


@router.post(
    "",
    response_model=CaseMaterialView,
    response_model_exclude_none=True,
    status_code=201,
)
def create(
    case_id: str,
    body: CaseMaterialCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return mount_material(database, case_id, body.materialId, body.revision, user)


@router.delete("/{material_id}", status_code=204)
def remove(
    case_id: str,
    material_id: str,
    revision: Annotated[int, Query(ge=1)],
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> Response:
    unmount_material(database, case_id, material_id, revision, user)
    return Response(status_code=204)
