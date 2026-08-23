from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DATABASE = "case_library_v3"
DEFAULT_MONGO_TIMEOUT_MS = 5000
DEFAULT_MONGO_MAX_POOL_SIZE = 100
DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_APP_ENVIRONMENT = "production"
DEFAULT_OBJECT_STORE_ENDPOINT = "localhost:9000"
DEFAULT_OBJECT_STORE_BUCKET = "case-library"
DEFAULT_AI_TIMEOUT_SECONDS = 60
DEFAULT_SEARCH_URL = "http://localhost:7700"
DEFAULT_SEARCH_INDEX_UID = "catalog"


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _mongo_environment() -> dict:
    return {
        "mongo_uri": os.getenv("MONGODB_URI", DEFAULT_MONGO_URI),
        "mongo_database": os.getenv("MONGODB_DB_NAME", DEFAULT_MONGO_DATABASE),
        "mongo_timeout_ms": int(
            os.getenv("MONGODB_TIMEOUT_MS", DEFAULT_MONGO_TIMEOUT_MS)
        ),
        "mongo_max_pool_size": int(
            os.getenv("MONGODB_MAX_POOL_SIZE", DEFAULT_MONGO_MAX_POOL_SIZE)
        ),
    }


def _session_environment() -> dict:
    return {
        "session_cookie_secure": _enabled(os.getenv("SESSION_COOKIE_SECURE", "true")),
        "session_ttl_seconds": int(
            os.getenv("SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS)
        ),
    }


def _object_store_environment() -> dict:
    return {
        "object_store_endpoint": os.getenv(
            "OBJECT_STORE_ENDPOINT", DEFAULT_OBJECT_STORE_ENDPOINT
        ),
        "object_store_bucket": os.getenv(
            "OBJECT_STORE_BUCKET", DEFAULT_OBJECT_STORE_BUCKET
        ),
        "object_store_access_key_file": os.getenv(
            "OBJECT_STORE_ACCESS_KEY_FILE", "/run/secrets/minio_root_user"
        ),
        "object_store_secret_key_file": os.getenv(
            "OBJECT_STORE_SECRET_KEY_FILE", "/run/secrets/minio_root_password"
        ),
        "object_store_secure": _enabled(os.getenv("OBJECT_STORE_SECURE")),
    }


def _ai_environment() -> dict:
    models = tuple(filter(None, map(str.strip, os.getenv("AI_MODELS", "").split(","))))
    return {
        "app_secret_file": os.getenv("APP_SECRET_FILE", "").strip(),
        "ai_base_url": os.getenv("AI_BASE_URL", "").strip(),
        "ai_api_key_file": os.getenv("AI_API_KEY_FILE", "").strip(),
        "ai_models": models,
        "ai_default_model": os.getenv("AI_DEFAULT_MODEL", "").strip(),
        "ai_timeout_seconds": int(
            os.getenv("AI_TIMEOUT_SECONDS", DEFAULT_AI_TIMEOUT_SECONDS)
        ),
    }


def _search_environment() -> dict:
    return {
        "search_url": os.getenv("SEARCH_URL", DEFAULT_SEARCH_URL).strip(),
        "search_index_uid": os.getenv(
            "SEARCH_INDEX_UID", DEFAULT_SEARCH_INDEX_UID
        ).strip(),
        "search_api_key_file": os.getenv("SEARCH_API_KEY_FILE", "").strip(),
    }


def _environment() -> dict:
    return {
        "app_environment": os.getenv("APP_ENV", DEFAULT_APP_ENVIRONMENT),
        "enable_demo_seed": _enabled(os.getenv("ENABLE_DEMO_SEED")),
        **_mongo_environment(),
        **_session_environment(),
        **_object_store_environment(),
        **_ai_environment(),
        **_search_environment(),
    }


@dataclass(frozen=True, slots=True)
class Settings:
    app_environment: str = DEFAULT_APP_ENVIRONMENT
    mongo_uri: str = DEFAULT_MONGO_URI
    mongo_database: str = DEFAULT_MONGO_DATABASE
    mongo_timeout_ms: int = DEFAULT_MONGO_TIMEOUT_MS
    mongo_max_pool_size: int = DEFAULT_MONGO_MAX_POOL_SIZE
    enable_demo_seed: bool = False
    session_cookie_secure: bool = True
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    object_store_endpoint: str = DEFAULT_OBJECT_STORE_ENDPOINT
    object_store_bucket: str = DEFAULT_OBJECT_STORE_BUCKET
    object_store_access_key_file: str = "/run/secrets/minio_root_user"
    object_store_secret_key_file: str = "/run/secrets/minio_root_password"
    object_store_secure: bool = False
    app_secret_file: str = ""
    ai_base_url: str = ""
    ai_api_key_file: str = ""
    ai_models: tuple[str, ...] = ()
    ai_default_model: str = ""
    ai_timeout_seconds: int = DEFAULT_AI_TIMEOUT_SECONDS
    search_url: str = DEFAULT_SEARCH_URL
    search_index_uid: str = DEFAULT_SEARCH_INDEX_UID
    search_api_key_file: str = ""

    def __post_init__(self) -> None:
        if self.app_environment.strip().lower() != "production":
            return
        if self.enable_demo_seed:
            raise ValueError("生产环境不能启用演示数据")
        if not self.session_cookie_secure:
            raise ValueError("生产环境必须启用 Secure Cookie")

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(**_environment())
