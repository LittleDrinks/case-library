#!/usr/bin/env python3
"""AI prompt and structured review routes."""

import json

from ai_client import AIClientError, AISettings, extract_json_object
from database import create_ai_review_version, get_case, split_paragraphs
from dependencies import (
    BearerCredentials,
    RequiredBearer,
    call_chat_completion,
    require_current_user,
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from prompt_registry.loader import render_prompt as render_registry_prompt
from prompts import get_prompt, list_prompt_metadata
from schemas import AIChatResponse, PromptListResponse
from security import get_case_owner_username, get_current_user

router = APIRouter()
AUTHOR_LOCKED_REVIEW_STATUSES = {"pending_review", "approved"}


def render_prompt(content: str, variables: dict) -> str:
    try:
        return content.format(**variables)
    except KeyError as exc:
        missing = exc.args[0]
        raise HTTPException(status_code=400, detail=f"缺少必填变量: {missing}") from exc


def _build_paragraph_review_prompt(case: dict, paragraphs: list[dict]) -> tuple[str, str]:
    prompt = get_prompt("alpha/paragraph-review")
    if prompt is None:
        raise RuntimeError("Missing runtime prompt: alpha/paragraph-review")
    user_payload = {
        "case": {
            "title": case.get("title", ""),
            "type": case.get("type", ""),
            "theme": case.get("theme", ""),
            "source_material": case.get("source_material", ""),
        },
        "paragraphs": paragraphs,
    }
    prompt_variables = {
        "title": user_payload["case"]["title"],
        "type": user_payload["case"]["type"],
        "theme": user_payload["case"]["theme"],
        "source_material": user_payload["case"]["source_material"],
        "content": json.dumps(user_payload, ensure_ascii=False),
    }
    user_content = render_registry_prompt(prompt, prompt_variables)
    return prompt.system_content, user_content


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

    prompt_id = payload.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise HTTPException(status_code=400, detail="缺少 prompt_id")

    prompt = get_prompt(prompt_id.strip())
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt 不存在")

    variables = payload.get("variables", {})
    if not isinstance(variables, dict):
        raise HTTPException(status_code=400, detail="variables 必须是对象")

    missing = [name for name in prompt.variables if name not in variables]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填变量: {', '.join(missing)}")

    allowed_variables = {name: variables[name] for name in prompt.variables}

    serialized_variables = json.dumps(allowed_variables, ensure_ascii=False)
    if len(serialized_variables) > 100_000:
        raise HTTPException(status_code=400, detail="AI 请求内容超过长度限制")

    settings = AISettings.from_env()
    if not settings.enabled:
        raise HTTPException(status_code=503, detail="AI 审核功能未启用")
    if not settings.configured():
        raise HTTPException(status_code=503, detail="AI 服务未配置")

    requested_model = payload.get("model")
    if requested_model is not None and not isinstance(requested_model, str):
        raise HTTPException(status_code=400, detail="model 必须是字符串")
    try:
        model = settings.resolve_model(requested_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    system_text = prompt.system_content
    user_payload = {
        "prompt_id": prompt.id,
        "task_input": render_prompt(prompt.content, allowed_variables),
        "variables": allowed_variables,
    }
    user_text = json.dumps(user_payload, ensure_ascii=False)
    try:
        answer = call_chat_completion(
            user_text, model, settings=settings, system_content=system_text
        )
    except AIClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    parsed = None
    parse_error = None
    if prompt.output_schema == "json":
        parsed, parse_error = extract_json_object(answer)

    return {
        "success": True,
        "answer": answer,
        "parsed": parsed,
        "parse_error": parse_error,
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
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    owner_username = get_case_owner_username(case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise HTTPException(status_code=403, detail="无权审核该案例")
    if (
        current_user.get("role") != "admin"
        and case.get("status") in AUTHOR_LOCKED_REVIEW_STATUSES
    ):
        raise HTTPException(
            status_code=403,
            detail="案例已提交审核或已通过，需退回修改后才能更新审核内容",
        )

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        payload = {}
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")

    settings = AISettings.from_env()
    if not settings.enabled:
        return JSONResponse(
            status_code=503,
            content={"success": False, "status": "disabled", "detail": "AI 审核功能未启用"},
        )
    if not settings.configured():
        return JSONResponse(
            status_code=503,
            content={"success": False, "status": "unconfigured", "detail": "AI 服务未配置"},
        )

    requested_model = payload.get("model")
    if requested_model is not None and not isinstance(requested_model, str):
        raise HTTPException(status_code=400, detail="model 必须是字符串")
    try:
        model = settings.resolve_model(requested_model)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "status": "invalid_model", "detail": str(exc)},
        )

    paragraphs = split_paragraphs(case.get("content", ""))
    system_text, user_text = _build_paragraph_review_prompt(case, paragraphs)
    try:
        answer = call_chat_completion(
            user_text, model, settings=settings, system_content=system_text
        )
    except AIClientError as exc:
        return JSONResponse(
            status_code=503,
            content={"success": False, "status": "unavailable", "detail": str(exc)},
        )

    parsed, parse_error = extract_json_object(answer)
    if parse_error:
        return JSONResponse(
            status_code=502,
            content={"success": False, "status": "parse_failed", "detail": parse_error},
        )

    try:
        version = create_ai_review_version(
            case_id,
            current_user.get("username", ""),
            parsed or {},
            model=model,
            raw_answer=answer,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"success": False, "status": "invalid_contract", "detail": str(exc)},
        )
    if not version:
        raise HTTPException(status_code=404, detail="案例不存在")

    return {
        "success": True,
        "status": "ok",
        "data": {
            "version": version,
            "comments": version.get("ai_review", {}).get("comments", []),
            "summary": version.get("ai_review", {}).get("summary", {}),
        },
    }
