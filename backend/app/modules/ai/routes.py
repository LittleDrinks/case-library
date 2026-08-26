from __future__ import annotations

import json
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import Settings
from app.core.dependencies import get_database, get_settings
from app.modules.ai.models import (
    AdminAISettingsUpdate,
    ChatRequest,
    ModelDiscoveryRequest,
    UserAISettingsUpdate,
)
from app.modules.ai.provider import OpenAICompatibleProvider, ProviderError
from app.modules.ai.quota import (
    AILease,
    AIQuotaError,
    acquire_chat_lease,
    acquire_discovery_lease,
)
from app.modules.ai.service import (
    AIConfigurationError,
    admin_settings_view,
    get_user_settings,
    resolve_provider,
    update_admin_settings,
    update_user_settings,
)
from app.modules.auth.dependencies import require_csrf, require_user

router = APIRouter(prefix="/api/ai", tags=["ai"])
admin_router = APIRouter(prefix="/api/admin/ai", tags=["ai"])
MAX_STREAM_BYTES = 256 * 1024
MAX_STREAM_SECONDS = 120


@router.get("/settings")
def show_settings(
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
):
    return get_user_settings(database, settings, user["id"])


@router.put("/settings")
def save_settings(
    body: UserAISettingsUpdate,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    try:
        return update_user_settings(database, settings, user["id"], body.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可配置平台模型")
    return user


@admin_router.get("/settings")
def show_admin_settings(
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    _user: dict = Depends(_admin),
):
    return admin_settings_view(database, settings)


@admin_router.put("/settings")
def save_admin_settings(
    body: AdminAISettingsUpdate,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    _user: dict = Depends(_admin),
    _session: dict = Depends(require_csrf),
):
    try:
        return update_admin_settings(
            database, settings, body.fallbackModel, _user["id"]
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _event(name: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"


def _stream_limit(size: int, started: float) -> None:
    if size > MAX_STREAM_BYTES or monotonic() - started > MAX_STREAM_SECONDS:
        raise AIQuotaError("AI 回答超过服务限制")


def _events(chunks, lease: AILease):
    size, started = 0, monotonic()
    try:
        for text in chunks:
            size += len(text.encode("utf-8"))
            _stream_limit(size, started)
            yield _event("token", {"text": text})
    except Exception:
        yield _event("error", {"message": "AI 服务暂不可用"})
        return
    finally:
        lease.release()
    yield _event("done", {})


def _provider(request: Request, selection):
    injected = getattr(request.app.state, "ai_provider", None)
    return injected or OpenAICompatibleProvider(
        selection.base_url,
        selection.api_key,
        selection.timeout_seconds,
        request.app.state.settings.app_environment == "test",
    )


def _discovery_provider(request: Request, body, settings: Settings):
    injected = getattr(request.app.state, "ai_discovery_provider", None)
    return injected or OpenAICompatibleProvider(
        body.baseUrl,
        body.apiKey,
        settings.ai_timeout_seconds,
        settings.app_environment == "test",
    )


@router.post("/models/discover")
def discover_models(
    body: ModelDiscoveryRequest,
    request: Request,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    try:
        lease = acquire_discovery_lease(database, user["id"], body.baseUrl)
    except AIQuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    try:
        models = _discovery_provider(request, body, settings).models()
        return {"models": list(dict.fromkeys(models))}
    except ProviderError as error:
        raise HTTPException(status_code=502, detail="无法获取模型列表") from error
    finally:
        lease.release()


def _chat_provider(database, settings, user_id):
    try:
        selected = resolve_provider(database, settings, user_id)
    except AIConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not selected:
        raise HTTPException(status_code=503, detail="AI 服务未配置")
    return selected


def _chat_lease(database, user_id, base_url):
    try:
        return acquire_chat_lease(database, user_id, base_url)
    except AIQuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error


@router.post("/chat")
def chat(
    body: ChatRequest,
    request: Request,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    selected = _chat_provider(database, settings, user["id"])
    lease = _chat_lease(database, user["id"], selected.base_url)
    messages = [message.model_dump() for message in body.messages]
    chunks = _provider(request, selected).chat(messages, selected.model)
    return StreamingResponse(_events(chunks, lease), media_type="text/event-stream")
