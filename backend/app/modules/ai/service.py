from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from app.modules.ai.crypto import (
    SecretCipherError,
    decrypt_api_key,
    encrypt_api_key,
)


class AIConfigurationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int


def _secret_available(path: str) -> bool:
    try:
        return bool(path and Path(path).read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _secret_value(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _platform_model(database, settings: Settings) -> tuple[str | None, str | None]:
    record = database.ai_platform_settings.find_one({"_id": "platform"}) or {}
    fallback = record.get("fallbackModel")
    if fallback in settings.ai_models:
        return fallback, "adminFallback"
    if settings.ai_default_model in settings.ai_models:
        return settings.ai_default_model, "default"
    return None, None


def _platform_configured(settings: Settings, model: str | None) -> bool:
    return bool(
        model and settings.ai_base_url and _secret_available(settings.ai_api_key_file)
    )


def get_user_settings(database, settings: Settings, user_id: str) -> dict:
    record = database.ai_user_settings.find_one({"_id": user_id})
    if record:
        return _custom_view(record)
    model, source = _platform_model(database, settings)
    configured = _platform_configured(settings, model)
    return _automatic_view(model, source, configured)


def _automatic_view(model: str | None, source: str | None, configured: bool) -> dict:
    return {
        "mode": "automatic",
        "baseUrl": None,
        "model": None,
        "hasApiKey": False,
        "configured": configured,
        "effectiveSource": source if configured else None,
        "effectiveModel": model if configured else None,
    }


def _custom_view(record: dict) -> dict:
    configured = bool(
        record.get("baseUrl") and record.get("model") and record.get("encryptedApiKey")
    )
    return {
        "mode": "custom",
        "baseUrl": record.get("baseUrl"),
        "model": record.get("model"),
        "hasApiKey": bool(record.get("encryptedApiKey")),
        "configured": configured,
        "effectiveSource": "custom" if configured else None,
        "effectiveModel": record.get("model") if configured else None,
    }


def admin_settings_view(database, settings: Settings) -> dict:
    record = database.ai_platform_settings.find_one({"_id": "platform"}) or {}
    model, _source = _platform_model(database, settings)
    return {
        "fallbackModel": record.get("fallbackModel"),
        "availableModels": list(settings.ai_models),
        "configured": _platform_configured(settings, model),
    }


def update_admin_settings(
    database,
    settings: Settings,
    model: str | None,
    user_id: str,
) -> dict:
    if model is not None and model not in settings.ai_models:
        raise ValueError("平台模型不可用")
    if model is None:
        database.ai_platform_settings.delete_one({"_id": "platform"})
    else:
        database.ai_platform_settings.replace_one(
            {"_id": "platform"}, _admin_record(model, user_id), upsert=True
        )
    return admin_settings_view(database, settings)


def _admin_record(model: str, user_id: str) -> dict:
    return {
        "_id": "platform",
        "fallbackModel": model,
        "updatedBy": user_id,
        "updatedAt": datetime.now(UTC),
    }


def _custom_selection(
    record: dict,
    settings: Settings,
    user_id: str,
) -> ProviderSelection:
    try:
        key = decrypt_api_key(
            bytes(record["encryptedApiKey"]), user_id, settings.app_secret_file
        )
        return ProviderSelection(
            record["baseUrl"], key, record["model"], settings.ai_timeout_seconds
        )
    except (KeyError, SecretCipherError) as error:
        raise AIConfigurationError("个人 AI 配置不可用") from error


def resolve_provider(
    database, settings: Settings, user_id: str
) -> ProviderSelection | None:
    record = database.ai_user_settings.find_one({"_id": user_id})
    if record:
        return _custom_selection(record, settings, user_id)
    model, _source = _platform_model(database, settings)
    api_key = _secret_value(settings.ai_api_key_file)
    if not model or not settings.ai_base_url or not api_key:
        return None
    return ProviderSelection(
        settings.ai_base_url, api_key, model, settings.ai_timeout_seconds
    )


def _normalized_url(value: str | None) -> str:
    return (value or "").strip().rstrip("/")


def _encrypted_key(
    body: dict,
    record: dict | None,
    settings: Settings,
    user_id: str,
    base_url: str,
):
    api_key = (body.get("apiKey") or "").strip()
    if api_key:
        try:
            return encrypt_api_key(api_key, user_id, settings.app_secret_file)
        except SecretCipherError as error:
            raise ValueError("应用密钥不可用") from error
    same_url = record and _normalized_url(record.get("baseUrl")) == base_url
    if same_url and record.get("encryptedApiKey"):
        return record["encryptedApiKey"]
    if record and record.get("encryptedApiKey"):
        raise ValueError("Base URL 变更后必须提供新的 API 密钥")
    raise ValueError("首次配置必须提供 API 密钥")


def _custom_record(body: dict, encrypted_key, user_id: str, base_url: str) -> dict:
    model = (body.get("model") or "").strip()
    if not base_url or not model:
        raise ValueError("自定义 AI 配置不完整")
    return {
        "_id": user_id,
        "baseUrl": base_url,
        "model": model,
        "encryptedApiKey": encrypted_key,
        "updatedAt": datetime.now(UTC),
    }


def update_user_settings(
    database, settings: Settings, user_id: str, body: dict
) -> dict:
    if body["mode"] == "automatic":
        database.ai_user_settings.delete_one({"_id": user_id})
        return get_user_settings(database, settings, user_id)
    current = database.ai_user_settings.find_one({"_id": user_id})
    base_url = _normalized_url(body.get("baseUrl"))
    encrypted_key = _encrypted_key(body, current, settings, user_id, base_url)
    record = _custom_record(body, encrypted_key, user_id, base_url)
    database.ai_user_settings.replace_one({"_id": user_id}, record, upsert=True)
    return get_user_settings(database, settings, user_id)
