from __future__ import annotations

import json
from asyncio import CancelledError
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import Settings
from app.core.dependencies import get_database, get_settings
from app.modules.ai.models import (
    AnnotationCandidates,
    WorkbenchChatRequest,
    WritingCandidate,
)
from app.modules.ai.quota import AILease
from app.modules.ai.routes import (
    _chat_lease,
    _chat_provider,
    _provider,
    _stream_limit,
)
from app.modules.ai.workbench import PromptTooLong, build_workbench_messages
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.cases.ai import load_workbench_snapshot


router = APIRouter(prefix="/api/cases/{case_id}/ai", tags=["case-ai"])
TEXT_MODES = {"chat", "find_sources"}
RESULT_MODELS = {
    "rewrite_selection": WritingCandidate,
    "rewrite_section": WritingCandidate,
    "resolve_annotation": WritingCandidate,
    "self_check": AnnotationCandidates,
}


def _event(name: str, payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"


def _result_model(mode: str):
    return RESULT_MODELS.get(mode)


def _text_events(provider, messages, model):
    size, started = 0, monotonic()
    for text in provider.chat(messages, model):
        size += len(text.encode("utf-8"))
        _stream_limit(size, started)
        yield _event("token", {"text": text})
    yield _event("done", {})


def _result_events(provider, messages, model, result_model):
    result = provider.structured(messages, model, result_model)
    validated = result_model.model_validate(result)
    yield _event("result", validated.model_dump())
    yield _event("done", {})


def _workbench_events(
    provider, messages, model, mode: str, lease: AILease
):
    try:
        if mode in TEXT_MODES:
            yield from _text_events(provider, messages, model)
        else:
            yield from _result_events(
                provider, messages, model, _result_model(mode)
            )
    except (Exception, CancelledError):
        yield _event("error", {"message": "AI 服务暂不可用"})
    finally:
        lease.release()


def _messages(body: WorkbenchChatRequest, snapshot: dict, target: dict):
    try:
        return build_workbench_messages(body, snapshot, target)
    except PromptTooLong as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/chat")
def chat(
    case_id: str,
    body: WorkbenchChatRequest,
    request: Request,
    database=Depends(get_database),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    snapshot, target = load_workbench_snapshot(database, case_id, body.context, user)
    messages = _messages(body, snapshot, target)
    selected = _chat_provider(database, settings, user["id"])
    lease = _chat_lease(database, user["id"], selected.base_url)
    provider = _provider(request, selected)
    events = _workbench_events(provider, messages, selected.model, body.mode, lease)
    return StreamingResponse(events, media_type="text/event-stream")
