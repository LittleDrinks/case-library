from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, TextUIPart
from starlette.responses import StreamingResponse

from app.core.dependencies import get_database, get_settings
from app.core.ids import new_id
from app.modules.agent.artifacts import decide_artifact
from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import (
    AgentRun,
    AgentSnapshot,
    AgentThread,
    AgentThreadSummary,
    ArtifactDecision,
)
from app.modules.agent.recovery import (
    LiveBuffer,
    events_stream,
    live_response,
    sse_headers,
)
from app.modules.agent.repository import (
    ActiveRunError,
    AgentRepository,
    MessageNotFoundError,
    ThreadNotFoundError,
)
from app.modules.agent.resources import CASE_EDIT_SKILL
from app.modules.agent.service import RunContext, load_history
from app.modules.agent.skills import case_edit_skill, reader_capability
from app.modules.ai.quota import AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.cases.published import published_view, version_readable
from app.modules.cases.service import get_case


router = APIRouter(prefix="/api/cases", tags=["agent"])
MAX_REQUEST_BYTES = 512 * 1024
MAX_MESSAGE_CHARACTERS = 20_000
MAX_THREAD_TITLE_CHARACTERS = 60


@dataclass(slots=True)
class Conversation:
    """单次对话操作的服务端上下文：作者工作稿或读者绑定的已发布版本。"""

    case: dict
    version_id: str | None
    reader: bool


@dataclass(slots=True)
class RunPlan:
    parts: list[dict]
    metadata: dict
    prompt: str
    skills: list[str]
    history: list
    client_request_id: str | None = None
    retry_message_id: str | None = None


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


def _existing_case(database, case_id: str) -> dict:
    case = database.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="案例不存在")
    return case


def _readable_case(case: dict, user: dict) -> bool:
    return case.get("publicationStatus") == "public" or user["role"] == "admin"


def _gate_case(database, case_id: str, user: dict) -> dict:
    """case 级门禁先于任何 Thread 枚举：不可读 404；非作者可读但未公开保持 403。"""
    case = _existing_case(database, case_id)
    if case["ownerId"] == user["id"] or _readable_case(case, user):
        if case["ownerId"] != user["id"] and case.get("publicationStatus") != "public":
            raise HTTPException(status_code=403, detail="仅案例作者可使用对话助手")
        return case
    raise HTTPException(status_code=404, detail="案例不存在")


def _readable_version(database, case: dict, version_id: str) -> dict:
    """读者对话只绑定真实已批准发布的版本；按当前身份即时重验可读性。"""
    version = database.case_versions.find_one({"id": version_id, "caseId": case["id"]})
    if not version or not version_readable(database, case, version_id, version, False):
        raise HTTPException(status_code=404, detail="案例版本不存在")
    return version


def _conversation(database, case_id: str, user: dict, version_id: str | None) -> Conversation:
    """versionId 缺省为作者工作稿上下文；给定则绑定实际可读的已发布版本。"""
    if not version_id:
        return Conversation(_editable_case(_author_case(database, case_id, user)), None, False)
    case = _gate_case(database, case_id, user)
    version = _readable_version(database, case, version_id)
    return Conversation(published_view(case, version), version_id, True)


def _thread_conversation(
    database, case_id: str, user: dict, repository: AgentRepository, thread_id: str
) -> tuple[Conversation, AgentThread]:
    """Thread 自身的绑定决定上下文；恢复/续跑/取消/事件全部即时重验可读性。"""
    case = _gate_case(database, case_id, user)
    thread = _thread(repository, thread_id, case_id, user["id"])
    if thread.version_id is None:
        if case["ownerId"] != user["id"]:
            raise HTTPException(status_code=403, detail="仅案例作者可使用对话助手")
        return Conversation(_editable_case(case), None, False), thread
    version = _readable_version(database, case, thread.version_id)
    return Conversation(published_view(case, version), thread.version_id, True), thread


@router.get("/{case_id}/agent/thread")
def show_thread(
    case_id: str,
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> AgentSnapshot:
    conversation = _conversation(database, case_id, user, version_id)
    repository = _repository(database)
    thread = repository.default_thread(case_id, user["id"], conversation.version_id)
    return repository.snapshot(thread)


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


def _skill_id(part) -> str | None:
    """从 data-skill 原子块提取 Skill 标识；其他类型返回 None。"""
    if not isinstance(part, DataUIPart) or part.type != "data-skill":
        return None
    skill_id = part.data.get("skillId") if isinstance(part.data, dict) else None
    if not isinstance(skill_id, str) or not skill_id:
        raise HTTPException(status_code=422, detail="AI 能力格式无效")
    return skill_id


def _latest_message(adapter: VercelAIAdapter):
    messages = adapter.run_input.messages
    if not messages:
        raise HTTPException(status_code=422, detail="消息不能为空")
    return messages[-1]


def _submit_prompt(adapter: VercelAIAdapter) -> tuple[list[dict], dict, str, str, list[str]]:
    if adapter.run_input.trigger != "submit-message":
        raise HTTPException(status_code=422, detail="只支持发送新消息或重试")
    latest = _latest_message(adapter)
    skills = [_skill_id(part) for part in latest.parts]
    if any(skill and skill != CASE_EDIT_SKILL.id for skill in skills):
        raise HTTPException(status_code=422, detail="AI 能力不可用")
    if latest.role != "user" or any(
        not isinstance(part, (TextUIPart, DataUIPart)) for part in latest.parts
    ):
        raise HTTPException(status_code=422, detail="消息必须是普通文本")
    text = "".join(part.text for part in latest.parts if isinstance(part, TextUIPart)).strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息不能为空")
    if len(text) > MAX_MESSAGE_CHARACTERS:
        raise HTTPException(status_code=422, detail="消息内容过长")
    parts = [part.model_dump(by_alias=True, mode="json", exclude_none=True) for part in latest.parts]
    return parts, {}, text, latest.id, [skill for skill in skills if skill]


def _retry_plan(repository, thread, adapter: VercelAIAdapter) -> RunPlan:
    """重试：引用原用户消息创建新 Run，不产生新消息。"""
    message_id = getattr(adapter.run_input, "message_id", None)
    message = repository.message(thread.id, message_id) if message_id else None
    if message is None or message.role != "user":
        raise HTTPException(status_code=422, detail="只能重试已发送的消息")
    parts = message.parts
    prompt = "".join(str(part.get("text") or "") for part in parts if part.get("type") == "text")
    skills = [
        part["data"]["skillId"] for part in parts
        if part.get("type") == "data-skill" and isinstance(part.get("data"), dict)
    ]
    return RunPlan(
        parts=parts, metadata=message.metadata, prompt=prompt,
        skills=[skill for skill in skills if skill == CASE_EDIT_SKILL.id],
        history=load_history(repository, thread, max_seq=message.message_seq),
        retry_message_id=message.id,
    )


def _run_plan(repository, thread, adapter: VercelAIAdapter) -> RunPlan:
    if adapter.run_input.trigger == "regenerate-message":
        return _retry_plan(repository, thread, adapter)
    parts, metadata, prompt, client_request_id, skills = _submit_prompt(adapter)
    return RunPlan(
        parts=parts, metadata=metadata, prompt=prompt, skills=skills,
        history=load_history(repository, thread), client_request_id=client_request_id,
    )


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


def _summary(thread: AgentThread) -> AgentThreadSummary:
    return AgentThreadSummary(
        id=thread.id,
        version_id=thread.version_id,
        title=thread.title,
        is_default=thread.is_default,
        running=thread.active_run_id is not None,
        event_seq=thread.event_seq,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _valid_title(raw: str | None) -> str | None:
    if raw is None:
        return None
    title = raw.strip()
    if not title:
        raise HTTPException(status_code=422, detail="对话标题不能为空")
    if len(title) > MAX_THREAD_TITLE_CHARACTERS:
        raise HTTPException(status_code=422, detail="对话标题过长")
    return title


def _default_title(text: str) -> str:
    return text.strip().splitlines()[0][:MAX_THREAD_TITLE_CHARACTERS]


class ThreadCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    versionId: str | None = None


class ThreadRenameBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str


@router.get("/{case_id}/agent/threads")
def list_threads(
    case_id: str,
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> list[AgentThreadSummary]:
    _conversation(database, case_id, user, version_id)
    threads = _repository(database).list_threads(case_id, user["id"], version_id or None)
    return [_summary(thread) for thread in threads]


@router.post("/{case_id}/agent/threads", status_code=201)
def create_thread(
    case_id: str,
    body: ThreadCreateBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> AgentThreadSummary:
    conversation = _conversation(database, case_id, user, body.versionId)
    repository = _repository(database)
    thread = repository.create_thread(
        case_id, user["id"], _valid_title(body.title), conversation.version_id
    )
    return _summary(thread)


@router.get("/{case_id}/agent/threads/{thread_id}")
def show_named_thread(
    case_id: str,
    thread_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> AgentSnapshot:
    repository = _repository(database)
    _, thread = _thread_conversation(database, case_id, user, repository, thread_id)
    return repository.snapshot(thread)


@router.patch("/{case_id}/agent/threads/{thread_id}")
def rename_thread(
    case_id: str,
    thread_id: str,
    body: ThreadRenameBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> AgentThreadSummary:
    repository = _repository(database)
    _, thread = _thread_conversation(database, case_id, user, repository, thread_id)
    title = _valid_title(body.title)
    try:
        thread = repository.rename_thread(thread_id, case_id, user["id"], title)
    except ThreadNotFoundError as error:
        raise HTTPException(status_code=404, detail="对话不存在") from error
    return _summary(thread)


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
    repository = _repository(database)
    conversation, thread = _thread_conversation(database, case_id, user, repository, thread_id)
    assistant_id = new_id("message")
    adapter = await _adapter(request, assistant_id)
    plan = _run_plan(repository, thread, adapter)
    if conversation.reader and plan.skills:
        raise HTTPException(status_code=422, detail="AI 能力不可用")
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    worker_id = request.app.state.agent_worker_id
    run = _start_run(repository, thread, user["id"], plan, assistant_id, lease, worker_id)
    context = _run_context(request, database, settings, user, conversation, repository,
                           thread, adapter, plan, run, selection, lease, worker_id)
    request.app.state.run_supervisor.start(context)
    return live_response(context.buffer)


def _run_context(request, database, settings, user, conversation: Conversation,
                 repository, thread, adapter, plan, run, selection, lease, worker_id):
    capabilities = _capabilities(conversation, plan)
    deps = ToolDeps(
        database=database, case_id=conversation.case["id"], thread_id=thread.id,
        run_id=run.id, user=user, catalog=request.app.state.search_catalog,
        catalog_state=request.app.state.catalog_state,
        secret_path=settings.app_secret_file,
    )
    return RunContext(
        repository, run, adapter, plan.history, plan.prompt, conversation.case,
        request.app.state.agent, buffer=LiveBuffer(),
        supervisor=request.app.state.run_supervisor,
        selection=selection, settings=settings, lease=lease, worker_id=worker_id,
        deps=deps, capabilities=capabilities, reader=conversation.reader,
    )


def _capabilities(conversation: Conversation, plan: RunPlan) -> list:
    if conversation.reader:
        return [reader_capability()]
    return [case_edit_skill()] if plan.skills else []


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


def _start_run(repository, thread, user_id, plan, assistant_id, lease, worker_id) -> AgentRun:
    try:
        return _create_run(repository, thread, user_id, plan, assistant_id, lease, worker_id)
    except ActiveRunError as error:
        if lease:
            lease.release()
        raise HTTPException(status_code=409, detail="当前对话已有运行任务") from error
    except MessageNotFoundError as error:
        _abort_start(lease)
        raise HTTPException(status_code=422, detail="只能重试已发送的消息") from error
    except Exception:
        _abort_start(lease)
        raise


def _create_run(repository, thread, user_id, plan, assistant_id, lease, worker_id):
    quota_ids = lease.quota_ids if lease else ()
    if plan.retry_message_id:
        run = repository.retry_run(
            thread, plan.retry_message_id, assistant_id,
            owner_id=worker_id, quota_ids=quota_ids,
        )
    else:
        run = repository.start_run(
            thread, user_id, plan.parts, plan.metadata, assistant_id,
            plan.client_request_id, owner_id=worker_id, quota_ids=quota_ids,
            default_title=_default_title(plan.prompt),
        )
    _bind_lease(repository, run, lease, worker_id)
    return run


def _bind_lease(repository, run, lease, worker_id) -> None:
    if not lease:
        return
    try:
        lease.bind_run(run.id)
    except Exception:
        repository.fail_run(run.id, worker_id)
        raise


def _abort_start(lease) -> None:
    if lease:
        lease.release()


@router.post("/{case_id}/agent/thread/{thread_id}/cancel")
def cancel_thread_run(
    case_id: str,
    thread_id: str,
    request: Request,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    """幂等取消：标记活动 Run 并触发本进程 cancellation token。"""
    repository = _repository(database)
    _, thread = _thread_conversation(database, case_id, user, repository, thread_id)
    run = repository.active_run(thread.id)
    if run is None:
        return {"runId": None, "status": "idle"}
    repository.request_cancel(run.id)
    request.app.state.run_supervisor.cancel_local(run.id)
    return {"runId": run.id, "status": "cancelling"}


@router.get("/{case_id}/agent/thread/{thread_id}/events")
def thread_events(
    case_id: str,
    thread_id: str,
    request: Request,
    after_seq: int | None = Query(default=None, alias="afterSeq"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
):
    """恢复流：按 Thread 游标 afterSeq/Last-Event-ID 只补发增量。"""
    repository = _repository(database)
    _, thread = _thread_conversation(database, case_id, user, repository, thread_id)
    cursor = after_seq if after_seq is not None else _last_event_id(request)
    if thread.active_run_id is None and cursor >= thread.event_seq:
        return Response(status_code=204)
    return live_event_response(repository, thread, max(cursor, 0))


def _last_event_id(request: Request) -> int:
    try:
        return int(request.headers.get("last-event-id", "0") or 0)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="事件游标无效") from error


def live_event_response(repository, thread, after_seq: int):
    return StreamingResponse(
        events_stream(repository, thread, after_seq),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


class ArtifactDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ArtifactDecision


@router.post("/{case_id}/agent/thread/{thread_id}/artifacts/{artifact_id}/decision")
def decide_thread_artifact(
    case_id: str,
    thread_id: str,
    artifact_id: str,
    body: ArtifactDecisionBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    _author_case(database, case_id, user)
    return decide_artifact(database, case_id, thread_id, artifact_id, user, body.decision)
