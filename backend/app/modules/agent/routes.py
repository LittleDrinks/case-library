from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, TextUIPart

from app.core.dependencies import get_database, get_settings
from app.core.ids import new_id
from app.modules.agent.artifacts import decide_artifact
from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import (
    AgentSnapshot,
    AgentThread,
    AgentThreadSummary,
    ArtifactDecision,
    AgentRun,
)
from app.modules.agent.repository import ActiveRunError, AgentRepository, ThreadNotFoundError
from app.modules.agent.resources import CASE_EDIT_SKILL
from app.modules.agent.service import RunContext, load_history, protocol_stream
from app.modules.agent.skills import case_edit_skill
from app.modules.agent.streaming import ClosableStreamingResponse
from app.modules.ai.quota import AILease, AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.cases.service import get_case


router = APIRouter(prefix="/api/cases", tags=["agent"])
MAX_REQUEST_BYTES = 512 * 1024
MAX_MESSAGE_CHARACTERS = 20_000
MAX_THREAD_TITLE_CHARACTERS = 60


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


def _skill_id(part) -> str | None:
    """从 data-skill 原子块提取 Skill 标识；其他类型返回 None。"""
    if not isinstance(part, DataUIPart) or part.type != "data-skill":
        return None
    skill_id = part.data.get("skillId") if isinstance(part.data, dict) else None
    if not isinstance(skill_id, str) or not skill_id:
        raise HTTPException(status_code=422, detail="AI 能力格式无效")
    return skill_id


def _prompt(adapter: VercelAIAdapter) -> tuple[list[dict], object, str, str, list[str]]:
    messages = adapter.run_input.messages
    if adapter.run_input.trigger != "submit-message" or not messages:
        raise HTTPException(status_code=422, detail="只支持发送新消息")
    latest = messages[-1]
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


class ThreadRenameBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str


@router.get("/{case_id}/agent/threads")
def list_threads(
    case_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> list[AgentThreadSummary]:
    _editable_case(_author_case(database, case_id, user))
    threads = _repository(database).list_threads(case_id, user["id"])
    return [_summary(thread) for thread in threads]


@router.post("/{case_id}/agent/threads", status_code=201)
def create_thread(
    case_id: str,
    body: ThreadCreateBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> AgentThreadSummary:
    _editable_case(_author_case(database, case_id, user))
    repository = _repository(database)
    thread = repository.create_thread(case_id, user["id"], _valid_title(body.title))
    return _summary(thread)


@router.get("/{case_id}/agent/threads/{thread_id}")
def show_named_thread(
    case_id: str,
    thread_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> AgentSnapshot:
    _editable_case(_author_case(database, case_id, user))
    repository = _repository(database)
    return repository.snapshot(_thread(repository, thread_id, case_id, user["id"]))


@router.patch("/{case_id}/agent/threads/{thread_id}")
def rename_thread(
    case_id: str,
    thread_id: str,
    body: ThreadRenameBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> AgentThreadSummary:
    _editable_case(_author_case(database, case_id, user))
    repository = _repository(database)
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
    case = _editable_case(_author_case(database, case_id, user))
    repository = _repository(database)
    thread = _thread(repository, thread_id, case_id, user["id"])
    assistant_id = new_id("message")
    adapter = await _adapter(request, assistant_id)
    parts, metadata, prompt, client_request_id, skills = _prompt(adapter)
    history = load_history(repository, thread)
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    worker_id = request.app.state.agent_worker_id
    run = _start_run(repository, thread, user["id"], parts, metadata, assistant_id,
                     client_request_id, lease, worker_id, _default_title(prompt))
    return _start_stream(_run_context(
        request, database, settings, user, case, repository, thread, adapter,
        history, prompt, run, selection, lease, worker_id, skills,
    ))


def _run_context(request, database, settings, user, case, repository, thread, adapter,
                 history, prompt, run, selection, lease, worker_id, skills):
    deps = ToolDeps(
        database=database, case_id=case["id"], thread_id=thread.id, run_id=run.id,
        user=user, catalog=request.app.state.search_catalog,
        catalog_state=request.app.state.catalog_state,
        secret_path=settings.app_secret_file,
    )
    return RunContext(
        repository, run, adapter, history, prompt, case,
        request.app.state.agent, selection, settings, lease, worker_id,
        deps=deps, capabilities=[case_edit_skill()] if skills else [],
    )


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
    client_request_id, lease: AILease | None, worker_id: str, default_title: str,
) -> AgentRun:
    try:
        return _create_run(
            repository, thread, user_id, parts, metadata, assistant_id,
            client_request_id, lease, worker_id, default_title,
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
    return ClosableStreamingResponse(response, stream)


def _create_run(
    repository, thread, user_id, parts, metadata, assistant_id, client_request_id,
    lease, worker_id, default_title,
):
    run = repository.start_run(
        thread, user_id, parts, metadata, assistant_id, client_request_id,
        owner_id=worker_id,
        quota_ids=lease.quota_ids if lease else (),
        default_title=default_title,
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


class ArtifactDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ArtifactDecision


@router.post("/{case_id}/agent/artifacts/{artifact_id}/decision")
def decide_case_artifact(
    case_id: str,
    artifact_id: str,
    body: ArtifactDecisionBody,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    _author_case(database, case_id, user)
    return decide_artifact(database, case_id, artifact_id, user, body.decision)
