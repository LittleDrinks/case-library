#!/usr/bin/env python3
"""FastAPI entry point for the case library."""

import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ai_client import call_chat_completion
from database import init_db
from dependencies import require_current_user
from routers import ai, auth, cases, public, reviews, static
from routers.ai import _build_paragraph_review_prompt, render_prompt
from schemas import AIChatRequest
from security import create_auth_token, get_current_user, verify_auth_token

__all__ = [
    "_build_paragraph_review_prompt",
    "call_chat_completion",
    "create_auth_token",
    "get_current_user",
    "render_prompt",
    "require_current_user",
    "verify_auth_token",
]


def parse_cors_origins(raw_value: str | None) -> list[str]:
    """Parse comma-separated CORS origins from environment configuration.

    No default origins are provided: production or unknown environments must
    explicitly set CORS_ALLOW_ORIGINS. Docker Compose and .env.example supply
    the local development defaults.
    """
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


app = FastAPI(
    title="Case Library API",
    version="1.0.0",
    description=(
        "Current implementation reference for the alpha case library API. "
        "Protected endpoints use an HMAC-signed bearer token returned by "
        "`POST /api/auth/login`; the token is not a JWT."
    ),
)

app.add_middleware(
    CORSMiddleware,
    **build_cors_options(),
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"success": False, "detail": str(exc)})


init_db()

app.include_router(auth.router)
app.include_router(ai.router)
app.include_router(cases.router)
app.include_router(reviews.router)
app.include_router(public.router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
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
    ai_review_operation = openapi_schema["paths"]["/api/cases/{case_id}/ai-review"]["post"]
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
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

static.mount_static(app)
app.include_router(static.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
