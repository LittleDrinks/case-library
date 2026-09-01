from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.core.config import Settings
from app.core.dependencies import get_database, get_settings
from app.modules.ai.adapter import (
    from_request,
    latest_text,
    stream_adapter,
    streaming_response,
)
from app.modules.ai.models import WorkbenchChatRequest
from app.modules.ai.quota import AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
from app.modules.ai.workbench import build_workbench_instructions
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.cases.ai import load_workbench_snapshot


router = APIRouter(prefix="/api/cases/{case_id}/ai", tags=["case-ai"])
MAX_REQUEST_BYTES = 512 * 1024


def _request_size(request: Request) -> None:
    try:
        size = int(request.headers.get("content-length", "0"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="请求格式无效") from error
    if size > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="请求内容过大")


def _body(adapter) -> WorkbenchChatRequest:
    raw = adapter.run_input.model_dump()
    fields = ("mode", "instruction", "history", "context")
    try:
        values = {key: raw[key] for key in fields if key in raw}
        return WorkbenchChatRequest.model_validate(values)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="工作台 AI 请求无效") from error


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


@router.post("/chat")
async def chat(
    case_id: str,
    request: Request,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    _request_size(request)
    adapter = await from_request(request, request.app.state.agent)
    body = _body(adapter)
    if latest_text(adapter) != body.instruction.strip():
        raise HTTPException(status_code=422, detail="工作台 AI 问题不一致")
    snapshot, target = load_workbench_snapshot(database, case_id, body.context, user)
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    instructions = build_workbench_instructions(body, snapshot, target)
    stream = stream_adapter(adapter, selection, settings, instructions, lease)
    return streaming_response(adapter, stream)
