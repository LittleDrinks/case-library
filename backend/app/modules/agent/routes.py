from __future__ import annotations

from functools import partial

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart
from starlette._utils import create_collapsing_task_group
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse

from app.core.dependencies import get_database, get_settings
from app.core.ids import new_id
from app.modules.agent.models import AgentRun, AgentSnapshot, AgentThread
from app.modules.agent.repository import ActiveRunError, AgentRepository, ThreadNotFoundError
from app.modules.agent.service import RunContext, load_history, protocol_stream
from app.modules.ai.quota import AILease, AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
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
    _editable_case(_author_case(database, case_id, user))
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


def _prompt(adapter: VercelAIAdapter) -> tuple[list[dict], object, str, str]:
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
    return parts, {}, text, latest.id


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
    settings=Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    return await _send_message(case_id, thread_id, request, database, settings, user)


async def _send_message(case_id, thread_id, request, database, settings, user):
    _request_size(request)
    case = _editable_case(_author_case(database, case_id, user))
    repository = _repository(database)
    thread = _thread(repository, thread_id, case_id, user["id"])
    assistant_id = new_id("message")
    adapter = await _adapter(request, assistant_id)
    parts, metadata, prompt, client_request_id = _prompt(adapter)
    history = load_history(repository, thread)
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    worker_id = request.app.state.agent_worker_id
    run = _start_run(repository, thread, user["id"], parts, metadata, assistant_id,
                     client_request_id, lease, worker_id)
    context = RunContext(
        repository, run, adapter, history, prompt, case,
        request.app.state.agent, selection, settings, lease, worker_id,
    )
    return _start_stream(context)


def _selection(database, settings, user_id: str):
    try:
        selection = resolve_provider(database, settings, user_id)
    except AIConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not selection and settings.app_environment != "test":
        raise HTTPException(status_code=503, detail="AI 服务未配置")
    return selection


def _lease(database, user_id: str, selection):
    if not selection:
        return None
    try:
        return acquire_chat_lease(database, user_id, selection.base_url)
    except AIQuotaError as error:
        raise HTTPException(status_code=429, detail=str(error)) from error


def _start_run(
    repository, thread: AgentThread, user_id, parts, metadata, assistant_id,
    client_request_id, lease: AILease | None, worker_id: str,
) -> AgentRun:
    try:
        return _create_run(
            repository, thread, user_id, parts, metadata, assistant_id,
            client_request_id, lease, worker_id,
        )
    except ActiveRunError as error:
        if lease:
            lease.release()
        raise HTTPException(status_code=409, detail="当前对话已有运行任务") from error
    except AIQuotaError as error:
        _abort_start(lease)
        raise HTTPException(status_code=503, detail="AI 服务暂不可用") from error
    except Exception:
        _abort_start(lease)
        raise


def _start_stream(context: RunContext):
    stream = protocol_stream(context)
    response = context.adapter.streaming_response(stream)
    return _ClosableStreamingResponse(response, stream)


async def _close_iterator(iterator) -> None:
    close = getattr(iterator, "aclose", None)
    if close:
        await close()


class _ClosableStreamingResponse(StreamingResponse):
    def __init__(self, response, source) -> None:
        super().__init__(
            response.body_iterator, response.status_code, dict(response.headers),
            response.media_type, response.background,
        )
        self._source = source

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.CancelScope(shield=True):
                await _close_iterator(self._source)
                await _close_iterator(self.body_iterator)

    async def _serve_with_disconnect(self, receive, send) -> None:
        async with create_collapsing_task_group() as task_group:

            async def run_and_cancel(func) -> None:
                await func()
                task_group.cancel_scope.cancel()

            task_group.start_soon(run_and_cancel, partial(self.stream_response, send))
            await run_and_cancel(partial(self.listen_for_disconnect, receive))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            await super().__call__(scope, receive, send)
            return
        try:
            await self._serve_with_disconnect(receive, send)
        except OSError as error:
            raise ClientDisconnect() from error
        if self.background is not None:
            await self.background()


def _create_run(
    repository, thread, user_id, parts, metadata, assistant_id, client_request_id, lease, worker_id
):
    run = repository.start_run(
        thread, user_id, parts, metadata, assistant_id, client_request_id,
        lease_data=lease.metadata() if lease else None, owner_id=worker_id,
    )
    try:
        if lease:
            lease.bind_run(run.id)
    except Exception:
        repository.fail_run(run.id, worker_id)
        raise
    return run


def _abort_start(lease) -> None:
    if lease:
        lease.release()
