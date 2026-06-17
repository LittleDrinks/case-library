#!/usr/bin/env python3
"""AI prompt and structured review routes."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.app.core.dependencies import (
    BearerCredentials,
    RequiredBearer,
    call_chat_completion,
    require_current_user,
)
from backend.app.core.security import get_current_user
from backend.app.domains.ai.prompts import list_prompt_metadata
from backend.app.domains.ai.schemas import AIChatResponse, PromptListResponse
from backend.app.domains.ai.service import (
    AIReviewResponseError,
    AIServiceHTTPError,
    ensure_case_ai_review_allowed,
    run_chat_prompt,
)
from backend.app.domains.ai.service import (
    _build_paragraph_review_prompt as build_paragraph_review_prompt_service,
)
from backend.app.domains.ai.service import (
    create_case_ai_review as create_case_ai_review_service,
)
from backend.app.domains.ai.service import (
    render_prompt as render_prompt_service,
)

router = APIRouter()


def _raise_ai_http_error(exc: AIServiceHTTPError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def render_prompt(content: str, variables: dict) -> str:
    try:
        return render_prompt_service(content, variables)
    except AIServiceHTTPError as exc:
        _raise_ai_http_error(exc)
    raise AssertionError("unreachable")


def _build_paragraph_review_prompt(case: dict, paragraphs: list[dict]) -> tuple[str, str]:
    return build_paragraph_review_prompt_service(case, paragraphs)


@router.get(
    "/api/prompts",
    response_model=PromptListResponse,
    summary="List AI prompt metadata",
    description=(
        "Return metadata for server-side AI self-check prompts. Prompt content and "
        "secrets are not returned. Requires a bearer token."
    ),
)
async def list_prompts(
    request: Request,
    category: str | None = None,
    _credentials: BearerCredentials = RequiredBearer,
):
    require_current_user(request)
    return {"success": True, "data": list_prompt_metadata(category)}


@router.post(
    "/api/ai/chat",
    response_model=AIChatResponse,
    summary="Run a server-side AI self-check prompt",
    description=(
        "Render one prompt from the prompt registry with caller-provided variables and "
        "send it through the server-side OpenAI-compatible chat client. Requires a "
        "bearer token and honors the AI_REVIEW_ENABLED feature flag."
    ),
)
async def ai_chat(
    request: Request,
    _credentials: BearerCredentials = RequiredBearer,
):
    require_current_user(request)
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="请求体必须是 JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")

    try:
        result = run_chat_prompt(payload, call_chat_completion=call_chat_completion)
    except AIServiceHTTPError as exc:
        _raise_ai_http_error(exc)

    return {
        "success": True,
        "answer": result["answer"],
        "parsed": result["parsed"],
        "parse_error": result["parse_error"],
    }


@router.post(
    "/api/cases/{case_id}/ai-review",
    summary="Create a version snapshot with structured AI paragraph comments",
    description=(
        "Owner/admin endpoint for teacher-side pre-submit self-check. The server "
        "generates paragraph ids, calls the configured AI model, validates the JSON "
        "comment contract, and stores the result on a read-only version snapshot."
    ),
)
async def create_case_ai_review(
    case_id: int,
    request: Request,
    _credentials: BearerCredentials = RequiredBearer,
):
    current_user = get_current_user(dict(request.headers))
    try:
        ensure_case_ai_review_allowed(case_id, current_user)
    except AIServiceHTTPError as exc:
        _raise_ai_http_error(exc)

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {}
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")

    try:
        result = create_case_ai_review_service(
            case_id,
            payload=payload,
            current_user=current_user,
            call_chat_completion=call_chat_completion,
        )
    except AIServiceHTTPError as exc:
        _raise_ai_http_error(exc)
    except AIReviewResponseError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_body(),
        )

    return {
        "success": True,
        "status": "ok",
        "data": {
            "version": result.version,
            "comments": result.comments,
            "summary": result.summary,
        },
    }
