"""Business orchestration for AI prompt and review workflows."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.ai_client import AIClientError, AISettings, extract_json_object
from backend.app.core.security import get_case_owner_username
from backend.app.domains.ai.prompts import get_prompt
from backend.app.domains.ai.prompts.loader import render_prompt as render_registry_prompt
from backend.app.domains.reviews.helpers import split_paragraphs
from backend.repositories.cases import get_case
from backend.repositories.versions import create_ai_review_version

AUTHOR_LOCKED_REVIEW_STATUSES = {"pending_review", "approved"}
ChatCompletionCallable = Callable[..., str]
AI_REVIEW_ERROR_DISABLED = "disabled"
AI_REVIEW_ERROR_UNCONFIGURED = "unconfigured"
AI_REVIEW_ERROR_INVALID_MODEL = "invalid_model"
AI_REVIEW_ERROR_UNAVAILABLE = "unavailable"
AI_REVIEW_ERROR_PARSE_FAILED = "parse_failed"
AI_REVIEW_ERROR_INVALID_CONTRACT = "invalid_contract"


class AIServiceHTTPError(Exception):
    """Domain error that should keep FastAPI's standard HTTP error body."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class AIReviewResponseError(Exception):
    """Domain error with the custom AI review response contract."""

    def __init__(self, status_code: int, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.status = status
        self.detail = detail

    def to_body(self) -> dict:
        return {"success": False, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class AIReviewResult:
    version: dict

    @property
    def comments(self) -> list:
        ai_review = self.version.get("ai_review")
        if not isinstance(ai_review, dict):
            return []
        comments = ai_review.get("comments", [])
        return comments if isinstance(comments, list) else []

    @property
    def summary(self) -> dict:
        ai_review = self.version.get("ai_review")
        if not isinstance(ai_review, dict):
            return {}
        summary = ai_review.get("summary", {})
        return summary if isinstance(summary, dict) else {}


@dataclass(frozen=True)
class AIReviewRequest:
    """Serializable request record for current sync execution and future queueing."""

    case_id: int
    requested_by: str
    requested_model: str | None
    case_snapshot: dict
    paragraphs: list[dict]
    prompt_id: str = "alpha/paragraph-review"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIReviewJob:
    """Rendered model job with enough data to run outside the HTTP request."""

    request: AIReviewRequest
    model: str
    settings: AISettings
    system_text: str
    user_text: str
    reuse_key: str


ReuseLookupCallable = Callable[[AIReviewJob], AIReviewResult | None]


def render_prompt(content: str, variables: dict) -> str:
    try:
        return content.format(**variables)
    except KeyError as exc:
        missing = exc.args[0]
        raise AIServiceHTTPError(400, f"缺少必填变量: {missing}") from exc


def _build_paragraph_review_prompt(case: dict, paragraphs: list[dict]) -> tuple[str, str]:
    prompt = get_prompt("alpha/paragraph-review")
    if prompt is None:
        raise RuntimeError("Missing runtime prompt: alpha/paragraph-review")
    case_payload = {
        "title": case.get("title", ""),
        "type": case.get("type", ""),
        "theme": case.get("theme", ""),
        "source_material": case.get("source_material", ""),
    }
    user_payload = {
        "case": case_payload,
        "paragraphs": paragraphs,
    }
    prompt_variables = {
        "title": case_payload["title"],
        "type": case_payload["type"],
        "theme": case_payload["theme"],
        "source_material": case_payload["source_material"],
        "content": json.dumps(user_payload, ensure_ascii=False),
    }
    user_content = render_registry_prompt(prompt, prompt_variables)
    return prompt.system_content, user_content


def _stable_review_reuse_key(request: AIReviewRequest, model: str) -> str:
    payload = {
        "case_id": request.case_id,
        "prompt_id": request.prompt_id,
        "model": model,
        "case": {
            "title": request.case_snapshot.get("title", ""),
            "type": request.case_snapshot.get("type", ""),
            "theme": request.case_snapshot.get("theme", ""),
            "content": request.case_snapshot.get("content", ""),
            "source_material": request.case_snapshot.get("source_material", ""),
        },
        "paragraphs": request.paragraphs,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def run_chat_prompt(
    payload: dict,
    *,
    call_chat_completion: ChatCompletionCallable,
) -> dict[str, Any]:
    prompt_id = payload.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise AIServiceHTTPError(400, "缺少 prompt_id")

    prompt = get_prompt(prompt_id.strip())
    if not prompt:
        raise AIServiceHTTPError(404, "Prompt 不存在")

    variables = payload.get("variables", {})
    if not isinstance(variables, dict):
        raise AIServiceHTTPError(400, "variables 必须是对象")

    missing = [name for name in prompt.variables if name not in variables]
    if missing:
        raise AIServiceHTTPError(400, f"缺少必填变量: {', '.join(missing)}")

    allowed_variables = {name: variables[name] for name in prompt.variables}

    serialized_variables = json.dumps(allowed_variables, ensure_ascii=False)
    if len(serialized_variables) > 100_000:
        raise AIServiceHTTPError(400, "AI 请求内容超过长度限制")

    settings = AISettings.from_env()
    if not settings.enabled:
        raise AIServiceHTTPError(503, "AI 审核功能未启用")
    if not settings.configured():
        raise AIServiceHTTPError(503, "AI 服务未配置")

    requested_model = payload.get("model")
    if requested_model is not None and not isinstance(requested_model, str):
        raise AIServiceHTTPError(400, "model 必须是字符串")
    try:
        model = settings.resolve_model(requested_model)
    except ValueError as exc:
        raise AIServiceHTTPError(400, str(exc)) from exc

    system_text = prompt.system_content
    user_payload = {
        "prompt_id": prompt.id,
        "task_input": render_prompt(prompt.content, allowed_variables),
        "variables": allowed_variables,
    }
    user_text = json.dumps(user_payload, ensure_ascii=False)
    try:
        answer = call_chat_completion(
            user_text,
            model,
            settings=settings,
            system_content=system_text,
        )
    except AIClientError as exc:
        raise AIServiceHTTPError(503, str(exc)) from exc

    parsed = None
    parse_error = None
    if prompt.output_schema == "json":
        parsed, parse_error = extract_json_object(answer)

    return {
        "answer": answer,
        "parsed": parsed,
        "parse_error": parse_error,
    }


def ensure_case_ai_review_allowed(case_id: int, current_user: dict | None) -> dict:
    """Return the target case after enforcing AI review permissions."""
    if not current_user:
        raise AIServiceHTTPError(401, "请先登录")

    case = get_case(case_id)
    if not case:
        raise AIServiceHTTPError(404, "案例不存在")
    owner_username = get_case_owner_username(case)
    if current_user.get("role") != "admin" and current_user.get("username") != owner_username:
        raise AIServiceHTTPError(403, "无权审核该案例")
    if (
        current_user.get("role") != "admin"
        and case.get("status") in AUTHOR_LOCKED_REVIEW_STATUSES
    ):
        raise AIServiceHTTPError(
            403,
            "案例已提交审核或已通过，需退回修改后才能更新审核内容",
        )
    return case


def create_ai_review_request(
    case_id: int,
    *,
    payload: dict,
    current_user: dict | None,
) -> AIReviewRequest:
    """Create the review request record after auth and request-body validation."""
    case = ensure_case_ai_review_allowed(case_id, current_user)
    if current_user is None:
        raise AIServiceHTTPError(401, "请先登录")

    requested_model = payload.get("model")
    if requested_model is not None and not isinstance(requested_model, str):
        raise AIServiceHTTPError(400, "model 必须是字符串")

    return AIReviewRequest(
        case_id=int(case_id),
        requested_by=str(current_user.get("username", "")),
        requested_model=requested_model,
        case_snapshot=dict(case),
        paragraphs=split_paragraphs(case.get("content", "")),
    )


def prepare_ai_review_job(
    request: AIReviewRequest,
    *,
    settings: AISettings | None = None,
) -> AIReviewJob:
    """Resolve runtime config and render the prompt for a queued or sync worker."""
    settings = settings or AISettings.from_env()
    if not settings.enabled:
        raise AIReviewResponseError(503, AI_REVIEW_ERROR_DISABLED, "AI 审核功能未启用")
    if not settings.configured():
        raise AIReviewResponseError(503, AI_REVIEW_ERROR_UNCONFIGURED, "AI 服务未配置")

    try:
        model = settings.resolve_model(request.requested_model)
    except ValueError as exc:
        raise AIReviewResponseError(400, AI_REVIEW_ERROR_INVALID_MODEL, str(exc)) from exc

    system_text, user_text = _build_paragraph_review_prompt(
        request.case_snapshot, request.paragraphs
    )
    return AIReviewJob(
        request=request,
        model=model,
        settings=settings,
        system_text=system_text,
        user_text=user_text,
        reuse_key=_stable_review_reuse_key(request, model),
    )


def call_ai_review_model(
    job: AIReviewJob,
    *,
    call_chat_completion: ChatCompletionCallable,
) -> str:
    try:
        return call_chat_completion(
            job.user_text,
            job.model,
            settings=job.settings,
            system_content=job.system_text,
        )
    except AIClientError as exc:
        raise AIReviewResponseError(503, AI_REVIEW_ERROR_UNAVAILABLE, str(exc)) from exc


def parse_ai_review_answer(answer: str) -> dict:
    parsed, parse_error = extract_json_object(answer)
    if parse_error:
        raise AIReviewResponseError(502, AI_REVIEW_ERROR_PARSE_FAILED, parse_error)
    return parsed or {}


def persist_ai_review_result(job: AIReviewJob, *, parsed: dict, raw_answer: str) -> AIReviewResult:
    try:
        version = create_ai_review_version(
            job.request.case_id,
            job.request.requested_by,
            parsed,
            model=job.model,
            raw_answer=raw_answer,
            case_snapshot=job.request.case_snapshot,
        )
    except ValueError as exc:
        raise AIReviewResponseError(422, AI_REVIEW_ERROR_INVALID_CONTRACT, str(exc)) from exc
    if not version:
        raise AIServiceHTTPError(404, "案例不存在")

    return AIReviewResult(version=version)


def run_ai_review_job(
    job: AIReviewJob,
    *,
    call_chat_completion: ChatCompletionCallable,
    reuse_lookup: ReuseLookupCallable | None = None,
) -> AIReviewResult:
    """Run one prepared AI review job.

    `reuse_lookup` is an explicit idempotency seam for a future worker/queue store.
    The current synchronous API passes no lookup, so existing POST behavior remains
    "create a new review version".
    """
    if reuse_lookup:
        reused = reuse_lookup(job)
        if reused is not None:
            return reused

    answer = call_ai_review_model(job, call_chat_completion=call_chat_completion)
    parsed = parse_ai_review_answer(answer)
    return persist_ai_review_result(job, parsed=parsed, raw_answer=answer)


def create_case_ai_review(
    case_id: int,
    *,
    payload: dict,
    current_user: dict | None,
    call_chat_completion: ChatCompletionCallable,
    reuse_lookup: ReuseLookupCallable | None = None,
) -> AIReviewResult:
    request = create_ai_review_request(
        case_id,
        payload=payload,
        current_user=current_user,
    )
    job = prepare_ai_review_job(request)
    return run_ai_review_job(
        job,
        call_chat_completion=call_chat_completion,
        reuse_lookup=reuse_lookup,
    )


__all__ = [
    "AI_REVIEW_ERROR_DISABLED",
    "AI_REVIEW_ERROR_INVALID_CONTRACT",
    "AI_REVIEW_ERROR_INVALID_MODEL",
    "AI_REVIEW_ERROR_PARSE_FAILED",
    "AI_REVIEW_ERROR_UNAVAILABLE",
    "AI_REVIEW_ERROR_UNCONFIGURED",
    "AUTHOR_LOCKED_REVIEW_STATUSES",
    "AIReviewJob",
    "AIReviewRequest",
    "AIReviewResponseError",
    "AIReviewResult",
    "AIServiceHTTPError",
    "ChatCompletionCallable",
    "ReuseLookupCallable",
    "_build_paragraph_review_prompt",
    "call_ai_review_model",
    "create_ai_review_request",
    "create_case_ai_review",
    "ensure_case_ai_review_allowed",
    "parse_ai_review_answer",
    "persist_ai_review_result",
    "prepare_ai_review_job",
    "render_prompt",
    "run_ai_review_job",
    "run_chat_prompt",
]
