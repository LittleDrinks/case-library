from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, TextUIPart
from starlette.responses import StreamingResponse

from app.core.dependencies import get_database, get_settings
from app.core.ids import new_id
from app.modules.agent.artifacts import decide_artifact
from app.modules.agent import prosemirror
from app.modules.agent.case_area import catalog_instructions, retained_sources, selection_from_parts
from app.modules.agent.deps import ToolDeps
from app.modules.agent.visibility import parts_projector, visible_snapshot
from app.modules.agent.models import (
    AgentRun,
    AgentSnapshot,
    AgentThread,
    AgentThreadSummary,
    ArtifactDecision,
    ArtifactTarget,
    write_view,
)
from app.modules.agent.writes import direct_write_requested, undo_write
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
from app.modules.agent.service import RunContext, load_history
from app.modules.agent.skills import (
    bound_skill_capability,
    domain_capability,
    reader_capability,
)
from app.modules.ai.quota import AIQuotaError, acquire_chat_lease
from app.modules.ai.service import AIConfigurationError, resolve_provider
from app.modules.auth.dependencies import require_csrf, require_user
from app.modules.cases.published import (
    published_view,
    version_readable,
    version_readable_by_id,
)
from app.modules.cases.service import case_view, get_case
from app.modules.skills.service import BoundSkill, SkillError, bind_published_skill


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
    selected: list[dict] = field(default_factory=list)
    selections: list[dict] = field(default_factory=list)


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
        return Conversation(_author_case(database, case_id, user), None, False)
    case = _gate_case(database, case_id, user)
    version = _readable_version(database, case, version_id)
    return Conversation(published_view(case, version), version_id, True)


def _editable_conversation(database, case_id: str, user: dict, version_id: str | None):
    conversation = _conversation(database, case_id, user, version_id)
    if not conversation.reader:
        _editable_case(conversation.case)
    return conversation


def _thread_conversation(
    database, case_id: str, user: dict, repository: AgentRepository, thread_id: str,
    version_id: str | None = None,
) -> tuple[Conversation, AgentThread]:
    """Thread 自身的绑定决定上下文；恢复/续跑/取消/事件全部即时重验可读性。"""
    case = _gate_case(database, case_id, user)
    thread = _thread(repository, thread_id, case_id, user["id"])
    _check_thread_version(thread, version_id)
    if thread.version_id is None:
        if case["ownerId"] != user["id"]:
            raise HTTPException(status_code=403, detail="仅案例作者可使用对话助手")
        return Conversation(case, None, False), thread
    version = _readable_version(database, case, thread.version_id)
    return Conversation(published_view(case, version), thread.version_id, True), thread


def _editable_thread_conversation(
    database, case_id: str, user: dict, repository: AgentRepository, thread_id: str,
    version_id: str | None = None,
):
    conversation, thread = _thread_conversation(
        database, case_id, user, repository, thread_id, version_id
    )
    if not conversation.reader:
        _editable_case(conversation.case)
    return conversation, thread


def _check_thread_version(thread: AgentThread, version_id: str | None) -> None:
    if version_id is not None and version_id != thread.version_id:
        raise HTTPException(status_code=409, detail="对话版本不匹配")


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
    snapshot = repository.snapshot(thread)
    return visible_snapshot(database, snapshot, user)


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
    if not isinstance(part, DataUIPart):
        return None
    if part.type != "data-skill":
        return None
    skill_id = part.data.get("skillId") if isinstance(part.data, dict) else None
    if not isinstance(skill_id, str) or not skill_id:
        raise HTTPException(status_code=422, detail="AI 能力格式无效")
    return skill_id


def _canonical_parts(parts) -> tuple[list[dict], list[str]]:
    skills, canonical = [], []
    for part in parts:
        if isinstance(part, DataUIPart):
            skill_id = _skill_id(part)
            if skill_id:
                skills.append(skill_id)
            else:
                canonical.append(part.model_dump(by_alias=True, mode="json", exclude_none=True))
        elif isinstance(part, TextUIPart):
            canonical.append(part.model_dump(by_alias=True, mode="json", exclude_none=True))
        else:
            raise HTTPException(status_code=422, detail="消息必须是普通文本")
    if len(skills) > 1:
        raise HTTPException(status_code=422, detail="一次消息只能选择一个 Skill")
    if skills:
        canonical.append({"type": "data-skill", "data": {"skillId": skills[0]}})
    return canonical, skills


def _stored_skill_ids(parts: list[dict]) -> list[str]:
    skills = [
        part["data"]["skillId"] for part in parts
        if part.get("type") == "data-skill"
        and isinstance(part.get("data"), dict)
        and isinstance(part["data"].get("skillId"), str)
    ]
    if len(skills) > 1:
        raise HTTPException(status_code=422, detail="一次消息只能选择一个 Skill")
    return skills


def _latest_message(adapter: VercelAIAdapter):
    messages = adapter.run_input.messages
    if not messages:
        raise HTTPException(status_code=422, detail="消息不能为空")
    return messages[-1]


def _submit_prompt(adapter: VercelAIAdapter) -> tuple[list[dict], dict, str, str, list[str]]:
    if adapter.run_input.trigger != "submit-message":
        raise HTTPException(status_code=422, detail="只支持发送新消息或重试")
    latest = _latest_message(adapter)
    if latest.role != "user":
        raise HTTPException(status_code=422, detail="消息必须是普通文本")
    parts, skills = _canonical_parts(latest.parts)
    text = "".join(part["text"] for part in parts if part["type"] == "text").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息不能为空")
    if len(text) > MAX_MESSAGE_CHARACTERS:
        raise HTTPException(status_code=422, detail="消息内容过长")
    return parts, {}, text, latest.id, skills


def _retry_plan(repository, thread, adapter: VercelAIAdapter, project) -> RunPlan:
    """重试：引用原用户消息创建新 Run，不产生新消息；历史同投影收敛。"""
    message_id = getattr(adapter.run_input, "message_id", None)
    message = repository.message(thread.id, message_id) if message_id else None
    if message is None or message.role != "user":
        raise HTTPException(status_code=422, detail="只能重试已发送的消息")
    parts = message.parts
    prompt = "".join(str(part.get("text") or "") for part in parts if part.get("type") == "text")
    skills = _stored_skill_ids(parts)
    return RunPlan(
        parts=parts, metadata=message.metadata, prompt=prompt,
        skills=[skill for skill in skills if skill],
        history=load_history(repository, thread, max_seq=message.message_seq, project=project),
        retry_message_id=message.id,
    )


def _run_plan(repository, thread, adapter: VercelAIAdapter, project) -> RunPlan:
    if adapter.run_input.trigger == "regenerate-message":
        return _retry_plan(repository, thread, adapter, project)
    parts, metadata, prompt, client_request_id, skills = _submit_prompt(adapter)
    return RunPlan(
        parts=parts, metadata=metadata, prompt=prompt, skills=skills,
        history=load_history(repository, thread, project=project),
        client_request_id=client_request_id,
    )


def _validate_plan(
    database, case: dict, plan: RunPlan, version_id: str | None = None
) -> RunPlan:
    plan.selected = selection_from_parts(database, case["id"], plan.parts, version_id)
    plan.selections = _document_selections(case.get("document") or {}, plan.parts)
    return plan


def _document_selections(document: dict, parts: list[dict]) -> list[dict]:
    return [_resolve_selection(document, part.get("data")) for part in parts
            if part.get("type") == "data-selection"]


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
    conversation = _editable_conversation(database, case_id, user, body.versionId)
    repository = _repository(database)
    thread = repository.create_thread(
        case_id, user["id"], _valid_title(body.title), conversation.version_id
    )
    return _summary(thread)


@router.get("/{case_id}/agent/threads/{thread_id}")
def show_named_thread(
    case_id: str,
    thread_id: str,
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
) -> AgentSnapshot:
    repository = _repository(database)
    _, thread = _thread_conversation(
        database, case_id, user, repository, thread_id, version_id
    )
    snapshot = repository.snapshot(thread)
    return visible_snapshot(database, snapshot, user)


@router.patch("/{case_id}/agent/threads/{thread_id}")
def rename_thread(
    case_id: str,
    thread_id: str,
    body: ThreadRenameBody,
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> AgentThreadSummary:
    repository = _repository(database)
    _, thread = _editable_thread_conversation(
        database, case_id, user, repository, thread_id, version_id
    )
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
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    settings=Depends(get_settings),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
):
    _request_size(request)
    return await _send_message(
        case_id, thread_id, request, database, settings, user, version_id
    )


async def _send_message(case_id, thread_id, request, database, settings, user, version_id=None):
    repository = _repository(database)
    conversation, thread = _editable_thread_conversation(
        database, case_id, user, repository, thread_id, version_id
    )
    assistant_id = new_id("message")
    adapter = await _adapter(request, assistant_id)
    plan = _plan_for(repository, thread, adapter, database, user, conversation)
    if conversation.reader and plan.skills:
        raise HTTPException(status_code=422, detail="AI 能力不可用")
    context = _start_context(
        request, database, settings, user, conversation, repository, thread,
        adapter, plan, assistant_id,
    )
    request.app.state.run_supervisor.start(context)
    return live_response(context.buffer)


def _plan_for(repository, thread, adapter, database, user, conversation):
    project = parts_projector(database, user, conversation.case["id"])
    return _validate_plan(
        database, conversation.case, _run_plan(repository, thread, adapter, project),
        conversation.version_id,
    )


def _resolve_skills(database, store, skill_ids: list[str]) -> tuple[BoundSkill, ...]:
    """Run 创建前把所选 Skill 固化为已发布版本快照；未发布/未知一律拒绝。"""
    if len(skill_ids) > 1:
        raise HTTPException(status_code=422, detail="一次消息只能选择一个 Skill")
    bounds: list[BoundSkill] = []
    for skill_id in dict.fromkeys(skill_ids):
        try:
            bounds.append(bind_published_skill(database, store, skill_id))
        except SkillError as error:
            raise HTTPException(status_code=422, detail="AI 能力不可用") from error
    return tuple(bounds)


def _start_context(
    request, database, settings, user, conversation, repository, thread, adapter, plan,
    assistant_id,
):
    lock = _run_lock_for(conversation, plan)
    bounds = _resolve_skills(database, request.app.state.blob_store, plan.skills)
    selection = _selection(database, settings, user["id"])
    lease = _lease(database, user["id"], selection)
    worker_id = request.app.state.agent_worker_id
    run = _start_run(repository, thread, user["id"], plan, assistant_id, lease,
                     worker_id, [bound.binding_record() for bound in bounds], lock)
    return _run_context(request, database, settings, user, conversation, repository,
                        thread, adapter, plan, run, selection, lease, worker_id, bounds)


def _run_lock_for(conversation: Conversation, plan: RunPlan):
    """Run 创建即冻结写入控制信息：基线修订号、锁定选区与直接写入授权。

    授权只来自服务端对当前教师消息文本的判定；读者对话永不授权。
    """
    if conversation.reader:
        return None, None, False
    plan.selections = _document_selections(
        conversation.case.get("document") or {}, plan.parts
    )
    base_revision, target = _run_lock(conversation.case, plan)
    return base_revision, target, direct_write_requested(plan.prompt)


def _run_context(request, database, settings, user, conversation: Conversation,
                 repository, thread, adapter, plan, run, selection, lease, worker_id, bounds):
    refs = retained_sources(database, conversation.case["id"], user, conversation.version_id)
    instructions = catalog_instructions(
        conversation.case.get("title") or "未命名案例", refs,
        plan.selected, plan.selections, conversation.reader,
    )
    deps = _run_deps(
        request, database, settings, user, conversation, thread, run, refs, plan
    )
    return RunContext(
        repository, run, adapter, plan.history, plan.prompt, conversation.case,
        request.app.state.agent, buffer=LiveBuffer(),
        supervisor=request.app.state.run_supervisor,
        selection=selection, settings=settings, lease=lease, worker_id=worker_id,
        deps=deps, bounds=bounds, capabilities=_capabilities(conversation, bounds),
        reader=conversation.reader,
        instructions=instructions,
    )


def _run_deps(request, database, settings, user, conversation, thread, run, refs, plan):
    return ToolDeps(
        database=database, case_id=conversation.case["id"], thread_id=thread.id,
        run_id=run.id, user=user, catalog=request.app.state.search_catalog,
        catalog_state=request.app.state.catalog_state, secret_path=settings.app_secret_file,
        store=request.app.state.blob_store, version_id=conversation.version_id,
        sources=refs, selected=plan.selected, selections=plan.selections,
    )


def _capabilities(conversation: Conversation, bounds) -> list:
    if conversation.reader:
        return [reader_capability()]
    return [domain_capability()] + [bound_skill_capability(bound) for bound in bounds]


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


def _run_lock(case: dict, plan: RunPlan) -> tuple[int | None, ArtifactTarget | None]:
    """Run 创建即锁定 baseRevision；仅当恰好一个非空选区时锁定目标范围。

    无选区不锁目标，提议修订将被拒绝，不由模型推断或自动锁定段落。
    """
    if len(plan.selections) != 1:
        return case.get("revision"), None
    row = plan.selections[0]
    return case.get("revision"), ArtifactTarget(
        from_pos=row["from"], to_pos=row["to"], quote=row["quote"],
    )

def _resolve_selection(document: dict, data: object) -> dict:
    from_pos = data.get("from") if isinstance(data, dict) else None
    to_pos = data.get("to") if isinstance(data, dict) else None
    if not isinstance(from_pos, int) or not isinstance(to_pos, int):
        raise HTTPException(status_code=422, detail="正文选区格式无效")
    try:
        prosemirror.selection_block(document, from_pos, to_pos)
    except prosemirror.ParagraphNotFoundError as error:
        raise HTTPException(
            status_code=422, detail="正文选区为空或跨越段落，请重新选择"
        ) from error
    return {
        "from": from_pos, "to": to_pos,
        "quote": prosemirror.text_between(document, from_pos, to_pos),
    }


def _start_run(repository, thread, user_id, plan, assistant_id, lease, worker_id,
               skill_bindings: list[dict[str, str]],
               lock: tuple[int | None, ArtifactTarget | None, bool] = (None, None, False)) -> AgentRun:
    try:
        return _create_run(
            repository, thread, user_id, plan, assistant_id, lease, worker_id,
            skill_bindings, lock,
        )
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


def _create_run(repository, thread, user_id, plan, assistant_id, lease, worker_id,
                skill_bindings: list[dict[str, str]],
                lock: tuple[int | None, ArtifactTarget | None, bool] = (None, None, False)):
    run_kwargs = _run_fields(lease, worker_id, skill_bindings, lock)
    if plan.retry_message_id:
        run = repository.retry_run(
            thread, plan.retry_message_id, assistant_id, **run_kwargs,
        )
    else:
        run = repository.start_run(
            thread, user_id, plan.parts, plan.metadata, assistant_id,
            plan.client_request_id, default_title=_default_title(plan.prompt),
            **run_kwargs,
        )
    _bind_lease(repository, run, lease, worker_id)
    return run


def _run_fields(lease, worker_id, skill_bindings, lock):
    quota_ids = lease.quota_ids if lease else ()
    base_revision, target, write_authorized = lock
    return {
        "owner_id": worker_id, "quota_ids": quota_ids,
        "skill_bindings": skill_bindings,
        "base_revision": base_revision, "target": target,
        "write_authorized": write_authorized,
    }


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
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    repository = _repository(database)
    _, thread = _thread_conversation(
        database, case_id, user, repository, thread_id, version_id
    )
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
    version_id: str | None = Query(default=None, alias="versionId"),
    database=Depends(get_database),
    user: dict = Depends(require_user),
):
    """恢复流：按 Thread 游标 afterSeq/Last-Event-ID 只补发增量。"""
    repository = _repository(database)
    conversation, thread = _thread_conversation(
        database, case_id, user, repository, thread_id, version_id
    )
    cursor = after_seq if after_seq is not None else _last_event_id(request)
    if thread.active_run_id is None and cursor >= thread.event_seq:
        return Response(status_code=204)
    return _event_response(database, user, repository, conversation, thread, cursor)


def _event_response(database, user, repository, conversation, thread, cursor):
    access_check = _event_access_check(database, conversation, thread)
    project = parts_projector(database, user, thread.case_id)
    return live_event_response(repository, thread, max(cursor, 0), access_check, project=project)


def _event_access_check(database, conversation: Conversation, thread: AgentThread):
    if not conversation.reader:
        return None
    return lambda: version_readable_by_id(database, thread.case_id, thread.version_id)


def _last_event_id(request: Request) -> int:
    try:
        return int(request.headers.get("last-event-id", "0") or 0)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="事件游标无效") from error


def live_event_response(repository, thread, after_seq: int, access_check=None, *, project):
    return StreamingResponse(
        events_stream(repository, thread, after_seq, access_check, project=project),
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


@router.post("/{case_id}/agent/thread/{thread_id}/writes/{write_id}/undo")
def undo_thread_write(
    case_id: str,
    thread_id: str,
    write_id: str,
    database=Depends(get_database),
    user: dict = Depends(require_user),
    _session: dict = Depends(require_csrf),
) -> dict:
    """撤销一次直接写入；仅作者且工作版本可编辑，重复撤销幂等返回。"""
    _author_case(database, case_id, user)
    result = undo_write(database, case_id, thread_id, write_id, user)
    return {"write": write_view(result["write"]), "case": case_view(result["case"])}
