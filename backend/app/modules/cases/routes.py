from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.dependencies import get_database, get_settings
from app.modules.auth.dependencies import optional_user, require_csrf, require_user
from app.modules.cases.lifecycle import execute_lifecycle, get_history
from app.modules.cases.models import (
    CaseCreate,
    CasePatch,
    LifecycleCommand,
    ManualVersionCreate,
)
from app.modules.cases.published import PublishedCaseReader, find_version, version_readable
from app.modules.cases.service import (
    CaseError,
    create_case,
    get_case,
    get_public_case,
    list_cases,
    list_drafts,
    update_case,
)
from app.modules.cases.sources import ordered_entries
from app.modules.cases.versions import create_manual_version
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


@router.get("/drafts")
def drafts(
    q: Annotated[str, Query()] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=50)] = 20,
    database=Depends(get_database),
    user: dict = Depends(require_user),
):
    return list_drafts(database, user, q, page, page_size)


@router.get("/{case_id}")
def detail(
    case_id: str,
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    return get_case(database, case_id, user)


@router.get("/{case_id}/public")
def public_detail(
    case_id: str,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    user: dict | None = Depends(optional_user),
):
    if not version_id:
        return get_public_case(database, case_id)
    case = _reader_case(database, case_id, user)
    return PublishedCaseReader(database).read_public_version(case, version_id)


@router.get("/{case_id}/sources")
def sources(
    case_id: str,
    request: Request,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    settings=Depends(get_settings),
    user: dict | None = Depends(optional_user),
):
    case = _reader_case(database, case_id, user)
    record = _sources_record(database, case, version_id or None, user)
    entries = ordered_entries(database, record, user, _origin(request, settings))
    return {"entries": entries}


@router.get("/{case_id}/public/export.docx")
def export_public_docx(
    case_id: str,
    request: Request,
    version_id: Annotated[str | None, Query(alias="versionId")] = None,
    database=Depends(get_database),
    settings=Depends(get_settings),
):
    _, record = _published_record(database, case_id, version_id)
    entries = ordered_entries(database, record, None, _origin(request, settings))
    return _docx_response(record, entries, case_id)


@router.get("/{case_id}/export.docx")
def export_docx(
    case_id: str,
    request: Request,
    database=Depends(get_database),
    settings=Depends(get_settings),
    user: dict | None = Depends(optional_user),
):
    case = _reader_case(database, case_id, user)
    record = _internal_record(database, case, user) or _published_record(
        database, case_id
    )[1]
    entries = ordered_entries(database, record, user, _origin(request, settings))
    return _docx_response(record, entries, case_id)


def _docx_response(case: dict, entries: list[dict], case_id: str) -> Response:
    headers = {"Content-Disposition": f'attachment; filename="case-{case_id}.docx"'}
    return Response(
        build_case_docx(case, entries),
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


@router.post("/{case_id}/versions")
def create_version(
    case_id: str,
    body: ManualVersionCreate,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return create_manual_version(
        database, case_id, body.title, user, body.revision,
    )


def _reader_case(database, case_id: str, user: dict | None) -> dict:
    case = database.cases.find_one({"id": case_id})
    internal = bool(
        user and (user["role"] == "admin" or (case or {}).get("ownerId") == user["id"])
    )
    if not case or (case["publicationStatus"] != "public" and not internal):
        raise CaseError(404, "案例不存在")
    return case


def _internal_record(database, case: dict, user: dict | None) -> dict | None:
    internal = _internal_reader(case, user)
    return case if internal else None


def _internal_reader(case: dict, user: dict | None) -> bool:
    return bool(
        user and (user["role"] == "admin" or case["ownerId"] == user["id"])
    ) and case["publicationStatus"] != "public"


def _published_record(
    database, case_id: str, version_id: str | None = None
) -> tuple[dict, dict]:
    case = database.cases.find_one({"id": case_id})
    target_id = version_id or (case or {}).get("publishedVersionId")
    if not case or case.get("publicationStatus") != "public" or not target_id:
        raise CaseError(404, "案例不存在")
    version = find_version(database, case, target_id, False)
    if not version or not version_readable(database, case, target_id, version, False):
        raise CaseError(404, "案例不存在")
    return case, version


def _sources_record(database, case: dict, version_id: str | None, user) -> dict:
    if version_id:
        return _version_record(database, case, version_id, user)
    return _internal_record(database, case, user) or _published_record(
        database, case["id"]
    )[1]


def _version_record(database, case: dict, version_id: str, user) -> dict:
    internal = _internal_reader(case, user)
    found = find_version(database, case, version_id, internal)
    if not found or not version_readable(database, case, version_id, found, internal):
        raise CaseError(404, "案例版本不存在")
    return found


def _origin(request: Request, settings) -> str:
    return settings.public_base_url or str(request.base_url).rstrip("/")
