from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import Settings
from app.core.dependencies import get_database, get_settings
from app.modules.ai.quota import AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.search.ai import (
    build_adapter,
    latest_query,
    parse_summary_request,
    stream_summary,
    summary_instructions,
    summary_response,
)


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


@router.post("/summary")
async def summary(
    request: Request,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    _request_size(request)
    adapter = await build_adapter(request, request.app.state.agent)
    body = parse_summary_request(adapter)
    if latest_query(adapter) != body.query:
        raise HTTPException(status_code=422, detail="检索摘要问题不一致")
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    stream = stream_summary(adapter, selection, settings, summary_instructions(body), lease)
    return summary_response(adapter, stream)
