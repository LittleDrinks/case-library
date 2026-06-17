#!/usr/bin/env python3
"""Canonical FastAPI application for the case library backend."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from backend.ai_client import call_chat_completion
from backend.app.api.router import api_router
from backend.app.api.routes import static
from backend.app.api.routes.ai import _build_paragraph_review_prompt, render_prompt
from backend.app.core.dependencies import require_current_user
from backend.app.core.security import create_auth_token, get_current_user, verify_auth_token
from backend.app.db.database import init_db
from backend.app.domains.ai.schemas import AIChatRequest

__all__ = [
    "_build_paragraph_review_prompt",
    "app",
    "build_cors_options",
    "call_chat_completion",
    "create_app",
    "create_auth_token",
    "get_current_user",
    "parse_cors_origins",
    "render_prompt",
    "require_current_user",
    "verify_auth_token",
]


def parse_cors_origins(raw_value: str | None) -> list[str]:
    """Parse comma-separated CORS origins from environment configuration."""
    if raw_value is None:
        return []
    return [origin.strip().rstrip("/") for origin in raw_value.split(",") if origin.strip()]


def build_cors_options() -> dict:
    allow_origins = parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS"))
    wildcard = "*" in allow_origins
    if wildcard:
        allow_origins = ["*"]
    return {
        "allow_origins": allow_origins,
        "allow_credentials": not wildcard,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def _install_custom_openapi(api: FastAPI) -> None:
    def custom_openapi():
        if api.openapi_schema:
            return api.openapi_schema

        openapi_schema = get_openapi(
            title=api.title,
            version=api.version,
            description=api.description,
            routes=api.routes,
        )
        ai_chat_operation = openapi_schema["paths"]["/api/ai/chat"]["post"]
        ai_chat_operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/AIChatRequest"},
                    "examples": {
                        "legacy_self_check": {
                            "summary": "Run a legacy compatibility self-check prompt",
                            "value": {
                                "prompt_id": "workflow/completeness",
                                "variables": {"title": "案例标题", "content": "案例正文"},
                                "model": "qwen-plus",
                            },
                        }
                    },
                }
            },
        }
        ai_review_operation = openapi_schema["paths"]["/api/cases/{case_id}/ai-review"][
            "post"
        ]
        ai_review_operation["requestBody"] = {
            "required": False,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Optional model name from AI_MODELS.",
                            }
                        },
                    },
                    "examples": {
                        "alpha_paragraph_review": {
                            "summary": "Create an alpha paragraph-comment review version",
                            "value": {"model": "qwen-plus"},
                        }
                    },
                }
            },
        }
        openapi_schema.setdefault("components", {}).setdefault("schemas", {})[
            "AIChatRequest"
        ] = AIChatRequest.model_json_schema(ref_template="#/components/schemas/{model}")
        api.openapi_schema = openapi_schema
        return api.openapi_schema

    api.openapi = custom_openapi  # type: ignore[method-assign]


def create_app() -> FastAPI:
    api = FastAPI(
        title="Case Library API",
        version="1.0.0",
        description=(
            "Current implementation reference for the alpha case library API. "
            "Protected endpoints use an HMAC-signed bearer token returned by "
            "`POST /api/auth/login`; the token is not a JWT."
        ),
    )

    api.add_middleware(
        CORSMiddleware,
        **build_cors_options(),
    )

    @api.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"success": False, "detail": str(exc)})

    init_db()

    api.include_router(api_router)
    _install_custom_openapi(api)
    static.mount_static(api)
    api.include_router(static.router)
    return api


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8001)  # nosec B104
