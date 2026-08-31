from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart

from app.core.dependencies import get_database
from app.core.ids import new_id
from app.modules.agent.models import AgentRun, AgentSnapshot, AgentThread
from app.modules.agent.repository import ActiveRunError, AgentRepository, ThreadNotFoundError
from app.modules.agent.service import RunContext, load_history, protocol_stream
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.cases.service import get_case


router = APIRouter(prefix="/api/cases", tags=["agent"])
MAX_REQUEST_BYTES = 512 * 1024
MAX_MESSAGE_CHARACTERS = 20_000


def _author_case(database, case_id: str, user: dict) -> dict:
    case = get_case(database, case_id, user)
    if case.get("ownerId") != user["id"]:
        raise HTTPException(status_code=403, detail="仅案例作者可使用对话助手")
    return case


def _editable_case(case: dict) -> dict:
    if case.get("workflowStatus") != "draft":
        raise HTTPException(status_code=409, detail="案例当前不可编辑")
    return case


def _repository(database) -> AgentRepository:
    return AgentRepository(database)


@router.get("/{case_id}/agent/thread")
def show_thread(
    case_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> AgentSnapshot:
    _author_case(database, case_id, user)
    repository = _repository(database)
    return repository.snapshot(repository.default_thread(case_id, user["id"]))


async def _adapter(request: Request, message_id: str):
    try:
        return await VercelAIAdapter.from_request(
            request,
            agent=request.app.state.agent,
            sdk_version=6,
            server_message_id=message_id,
            manage_system_prompt="server",
            allow_uploaded_files=False,
        )
    except (ValidationError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="AI 消息格式无效") from error


def _prompt(adapter: VercelAIAdapter) -> tuple[list[dict], object, str]:
    messages = adapter.run_input.messages
    if adapter.run_input.trigger != "submit-message" or not messages:
        raise HTTPException(status_code=422, detail="只支持发送新消息")
    latest = messages[-1]
    if latest.role != "user" or any(not isinstance(part, TextUIPart) for part in latest.parts):
        raise HTTPException(status_code=422, detail="消息必须是普通文本")
    text = "".join(part.text for part in latest.parts).strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息不能为空")
    if len(text) > MAX_MESSAGE_CHARACTERS:
        raise HTTPException(status_code=422, detail="消息内容过长")
    parts = [part.model_dump(by_alias=True, mode="json", exclude_none=True) for part in latest.parts]
    return parts, {}, text


def _request_size(request: Request) -> None:
    try:
        size = int(request.headers.get("content-length", "0"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="请求格式无效") from error
    if size > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="请求内容过大")


def _thread(repository, thread_id: str, case_id: str, user_id: str) -> AgentThread:
    try:
        return repository.thread(thread_id, case_id, user_id)
    except ThreadNotFoundError as error:
        raise HTTPException(status_code=404, detail="对话不存在") from error


@router.post("/{case_id}/agent/thread/{thread_id}/stream")
async def send_message(
    case_id: str,
    thread_id: str,
    request: Request,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return await _send_message(case_id, thread_id, request, database, user)


async def _send_message(case_id, thread_id, request, database, user):
    _request_size(request)
    case = _editable_case(_author_case(database, case_id, user))
    repository = _repository(database)
    thread = _thread(repository, thread_id, case_id, user["id"])
    assistant_id = new_id("message")
    adapter = await _adapter(request, assistant_id)
    parts, metadata, prompt = _prompt(adapter)
    history = load_history(repository, thread)
    run = _start_run(repository, thread, user["id"], parts, metadata, assistant_id)
    context = RunContext(
        repository, run, adapter, history, prompt, case,
        request.app.state.agent,
    )
    return _start_stream(context)


def _start_run(
    repository, thread: AgentThread, user_id, parts, metadata, assistant_id
) -> AgentRun:
    try:
        return repository.start_run(thread, user_id, parts, metadata, assistant_id)
    except ActiveRunError as error:
        raise HTTPException(status_code=409, detail="运行任务无法创建") from error


def _start_stream(context: RunContext):
    try:
        return context.adapter.streaming_response(protocol_stream(context))
    except Exception:
        context.repository.fail_run(context.run.id)
        raise
