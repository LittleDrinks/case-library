from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import Settings
from app.core.dependencies import get_database, get_settings
from app.modules.ai.models import (
    AdminAISettingsUpdate,
    ModelDiscoveryRequest,
    UserAISettingsUpdate,
)
from app.modules.ai.provider import OpenAIModelDiscovery, ProviderError
from app.modules.ai.quota import (
    AIQuotaError,
    acquire_discovery_lease,
)
from app.modules.ai.service import (
    admin_settings_view,
    get_user_settings,
    update_admin_settings,
    update_user_settings,
)
from app.modules.auth.dependencies import require_csrf, require_user

router = APIRouter(prefix="/api/ai", tags=["ai"])
admin_router = APIRouter(prefix="/api/admin/ai", tags=["ai"])


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


def _discovery_provider(request: Request, body, settings: Settings):
    injected = getattr(request.app.state, "ai_discovery_provider", None)
    return injected or OpenAIModelDiscovery(
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
