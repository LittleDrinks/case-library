from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import Settings
from app.core.dependencies import (
    get_catalog_state,
    get_database,
    get_search_catalog,
    get_settings,
)
from app.modules.ai.quota import AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
from app.modules.agent.search import source_ref
from app.modules.agent.source_reader import revalidate_sources
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.auth.sessions import load_current_user
from app.modules.materials.service import campus_verified
from app.modules.search.ai import (
    build_adapter,
    latest_query,
    parse_summary_request,
    stream_summary,
    summary_instructions,
    summary_response,
)
from app.modules.search.service import CatalogSearch, search_catalog_with_public_scope


router = APIRouter(prefix="/api/search", tags=["search"])
MAX_REQUEST_BYTES = 512 * 1024


def _request_size(request: Request) -> None:
    try:
        size = int(request.headers.get("content-length", "0"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="请求格式无效") from error
    if size > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="请求内容过大")


def _selection(database, settings: Settings, user_id: str):
    try:
        selection = resolve_provider(database, settings, user_id)
    except AIConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not selection and settings.app_environment != "test":
        raise HTTPException(status_code=503, detail="AI 服务未配置")
    return selection


def _lease(database, user_id: str, selection):
    if not selection:
        return None
    try:
        return acquire_chat_lease(database, user_id, selection.base_url)
    except AIQuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error


def _campus_only_search_results(
    items: list[dict], public_items: list[dict] | None,
) -> bool:
    if public_items is None:
        return False
    public_sources = {
        (item["kind"], item["id"]): item
        for item in public_items
    }
    for item in items:
        public_match = public_sources.get((item["kind"], item["id"]))
        if item["kind"] == "case" and public_match is None:
            return True
        if item["kind"] == "material" and item.get("contentAvailable") is True:
            if not public_match or public_match.get("contentAvailable") is not True:
                return True
    return False


def _summary_sources_current(
    database, user: dict, items: list[dict], campus_only_results: bool,
) -> bool:
    current_user = load_current_user(database, user)
    if current_user is None:
        return False
    if campus_only_results and not campus_verified(current_user):
        return False
    refs = [source_ref(item, database) for item in items]
    return revalidate_sources(database, user, "", refs)


@router.post("/summary")
async def summary(
    request: Request,
    database=Depends(get_database),
    catalog=Depends(get_search_catalog),
    catalog_state=Depends(get_catalog_state),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    _request_size(request)
    adapter = await build_adapter(request, request.app.state.agent)
    body = parse_summary_request(adapter)
    if latest_query(adapter) != body.query:
        raise HTTPException(status_code=422, detail="检索摘要问题不一致")
    results, public_results = search_catalog_with_public_scope(
        database,
        catalog,
        catalog_state,
        CatalogSearch(body.search, user, settings.app_secret_file),
    )
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    items = results["items"][:15]
    campus_only_results = _campus_only_search_results(
        items,
        public_results,
    )
    instructions = summary_instructions(body, items)

    def access_check() -> bool:
        return _summary_sources_current(
            database, user, items, campus_only_results
        )

    stream = stream_summary(
        adapter, selection, settings, instructions, lease,
        access_check=access_check,
    )
    return summary_response(adapter, stream)
