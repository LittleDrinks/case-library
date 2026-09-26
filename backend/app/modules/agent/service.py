from __future__ import annotations

import asyncio
import logging
import os
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic_ai import CancellationToken, capture_run_messages
from pydantic_ai.exceptions import ModelRetry, RunCancelled, ToolRetryError, UnexpectedModelBehavior
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent, ModelResponse
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import UIMessage
from pydantic_ai.ui.vercel_ai.response_types import ErrorChunk

from app.modules.agent.models import AgentMessage, AgentRun, AgentThread, TerminalRunStatus
from app.modules.agent.deps import ToolDeps
from app.modules.agent.repository import (
    AgentRepository,
    review_baseline_current,
    review_delivery_allowed,
)
from app.modules.agent.resources import READER_PROMPT, REVIEW_PROMPT, SYSTEM_PROMPT, resource_record
from app.modules.agent.runtime import case_instructions
from app.modules.ai.provider import open_model
from app.modules.ai.quota import AIQuotaError
from app.modules.cases.published import version_readable_by_id


RUN_HEARTBEAT_SECONDS = float(os.getenv("AGENT_RUN_HEARTBEAT_SECONDS", "5"))
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunContext:
    repository: AgentRepository
    run: AgentRun
    adapter: VercelAIAdapter
    history: list
    prompt: str
    case: dict
    agent: object
    buffer: object = None
    supervisor: object = None
    selection: object | None = None
    settings: object | None = None
    lease: object | None = None
    worker_id: str | None = None
    result: object | None = None
    token: CancellationToken | None = None
    deps: ToolDeps | None = None
    capabilities: list | None = None
    bounds: tuple = ()
    instructions: str = ""
    reader: bool = False
    review: bool = False
    cancelled: bool = False
    failed: bool = False
    lost: bool = False
    lease_released: bool = False
    tool_timings: dict[str, dict[str, str]] = field(default_factory=dict)
    captured_messages: list = field(default_factory=list)
    failure: Exception | None = None


def _run_kwargs(context: RunContext, model=None) -> dict:
    database = context.deps.database if context.deps else None
    values = {
        "message_history": context.history,
        "conversation_id": context.run.thread_id,
        "run_id": context.run.id,
        "instructions": case_instructions(
            context.case, database=database, extra=context.instructions,
            reader=context.reader, review=context.review,
        ),
        "user_prompt": context.prompt,
        "deps": context.deps,
        "cancellation_token": context.token,
    }
    if context.capabilities:
        values["capabilities"] = context.capabilities
    if model is not None:
        values["model"] = model
    return values


def _record_tool_event(context: RunContext, event) -> None:
    if isinstance(event, FunctionToolCallEvent):
        part = event.part
        timing = {"toolCallId": part.tool_call_id, "toolName": part.tool_name,
                  "startedAt": datetime.now(UTC).isoformat()}
        context.tool_timings[part.tool_call_id] = timing
    elif isinstance(event, FunctionToolResultEvent):
        part = event.part
        timing = context.tool_timings.get(part.tool_call_id)
        if timing:
            timing["finishedAt"] = (part.timestamp or datetime.now(UTC)).isoformat()
    else:
        return
    if context.tool_timings.get(event.part.tool_call_id):
        context.repository.record_tool_timing(
            context.run.id, context.tool_timings[event.part.tool_call_id], context.worker_id
        )


async def _native_events(context: RunContext):
    try:
        with capture_run_messages() as messages:
            context.captured_messages = messages
            async with _model_context(context) as model:
                async with context.agent.run_stream_events(**_run_kwargs(context, model)) as events:
                    async for event in events:
                        _record_tool_event(context, event)
                        yield event
    except (RunCancelled, asyncio.CancelledError):
        context.cancelled = True
        raise
    except Exception as error:
        context.failed = True
        context.failure = error
        logger.warning("Agent run %s failed: %s; cause=%s", context.run.id,
                       type(error).__name__, type(error.__cause__).__name__)
        raise


class _NoModel:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *_args):
        return None


def _model_context(context: RunContext):
    if not context.selection:
        return _NoModel()
    allow_internal = context.settings.app_environment == "test"
    return open_model(context.selection, allow_internal, thinking=True)


def _message_id(assistant_id: str, user_id: str):
    def generate(_message, role, _index):
        return assistant_id if role == "assistant" else user_id

    return generate


def _dump_messages(context: RunContext, result):
    return VercelAIAdapter.dump_messages(
        result.new_messages() if result is not None else context.captured_messages[len(context.history):],
        generate_message_id=_message_id(
            context.run.assistant_message_id, context.run.user_message_id
        ),
        sdk_version=6,
    )


def _assistant_parts(assistant) -> list[dict]:
    return [
        part.model_dump(by_alias=True, mode="json", exclude_none=True)
        for part in assistant.parts
    ]


def _loaded_capability_ids(parts: list[dict]) -> list[str]:
    """从 load_capability 工具调用中提取模型实际加载的能力标识。"""
    ids = []
    for part in parts:
        if part.get("type") != "tool-load_capability":
            continue
        data = part.get("input")
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            ids.append(data["id"])
    return ids


def _task_prompt(reader: bool, review: bool) -> str:
    if review:
        return REVIEW_PROMPT
    return READER_PROMPT if reader else SYSTEM_PROMPT


def _run_resources(parts: list[dict], bounds: tuple = (), reader=False,
                   review=False) -> list[dict[str, str]]:
    records = [resource_record(SYSTEM_PROMPT)]
    task_prompt = _task_prompt(reader, review)
    if task_prompt is not SYSTEM_PROMPT:
        records.append(resource_record(task_prompt))
    loaded = {bound.skill_id for bound in bounds} if review else set(_loaded_capability_ids(parts))
    return [*records, *[bound.resource_record() for bound in bounds if bound.skill_id in loaded]]


def _assistant_ui(context: RunContext, result):
    """把一次 Run 的全部 assistant 步骤合并为单条 UI 消息。"""
    dumped = _dump_messages(context, result)
    parts = [
        part for message in dumped if message.role == "assistant" for part in message.parts
    ]
    assistant = next((message for message in dumped if message.role == "assistant"), None)
    if assistant is None:
        raise RuntimeError("AI 响应为空")
    return assistant.model_copy(update={"parts": parts})


def _assistant_message(context: RunContext, result) -> AgentMessage:
    assistant = _assistant_ui(context, result)
    return AgentMessage(
        id=assistant.id, thread_id=context.run.thread_id, run_id=context.run.id,
        role="assistant", metadata=assistant.metadata, parts=_assistant_parts(assistant),
        created_at=datetime.now(UTC),
    )


def _assistant_parts_of(context: RunContext) -> list[dict]:
    return _assistant_parts(_assistant_ui(context, context.result))


def _partial_assistant(context: RunContext, saved_artifact_ids: frozenset[str] = frozenset()) -> AgentMessage | None:
    messages = context.captured_messages[len(context.history):]
    if not _reader_accessible(context) or not any(
        isinstance(message, ModelResponse) and message.parts for message in messages
    ):
        return None
    assistant = _assistant_message(context, None)
    return assistant.model_copy(update={"parts": [_interrupted_part(part, saved_artifact_ids) for part in assistant.parts]})


def _interrupted_part(part: dict, saved_artifact_ids: frozenset[str]) -> dict:
    if part.get("state") == "approval-requested":
        reason = "运行已结束，工具未完成"
    elif (part.get("type") in {"tool-propose_revision", "tool-propose_document"}
          and part.get("state") == "output-available"
          and part.get("output", {}).get("artifactId") not in saved_artifact_ids):
        reason = "运行未完成，修改建议未保存"
    else:
        return part
    result = {key: value for key, value in part.items() if key not in {"approval", "output"}}
    return {**result, "state": "output-error", "errorText": reason}


def _failure_message(context: RunContext) -> str:
    error = context.failure
    if isinstance(error, UnexpectedModelBehavior):
        if context.tool_timings and isinstance(error.__cause__, (ModelRetry, ToolRetryError)):
            return "AI 未能完成工具调用，请调整要求后重试"
        return "AI 返回内容不符合要求，请重试"
    return "AI 服务暂不可用"


async def _drain(context: RunContext) -> None:
    try:
        async with aclosing(_adapter_stream(context)) as stream:
            async for chunk in stream:
                if not _reader_accessible(context):
                    _revoke_reader(context)
                    return
                if isinstance(chunk, ErrorChunk):
                    chunk = chunk.model_copy(update={"error_text": _failure_message(context)})
                await context.buffer.publish(chunk)
    except (RunCancelled, asyncio.CancelledError):
        context.cancelled = True
    except Exception:
        context.failed = True


def _adapter_stream(context: RunContext):
    return context.adapter.transform_stream(
        _native_events(context),
        on_complete=lambda result: _on_complete(context, result),
        on_cancel=lambda cancelled: _on_cancel(context, cancelled),
    )


async def _on_complete(context: RunContext, result) -> None:
    context.result = result


async def _on_cancel(context: RunContext, _cancelled) -> None:
    context.cancelled = True


async def execute_run(context: RunContext, supervisor) -> None:
    """后台执行一次 Run：断开不取消，终态由显式停止、完成或失败决定。"""
    context.token = CancellationToken()
    monitor = asyncio.create_task(_monitor(context, asyncio.current_task()))
    try:
        await _drain(context)
    finally:
        monitor.cancel()
        _finalize(context)
        if context.supervisor is not None:
            context.supervisor.unregister(context.run.id)
        await context.buffer.close()


def _stream_status(context: RunContext) -> TerminalRunStatus:
    if context.failed:
        return "failed"
    if context.cancelled:
        return "cancelled"
    return "completed" if context.result is not None else "failed"


async def _monitor(context: RunContext, owner_task) -> None:
    try:
        while True:
            await asyncio.sleep(RUN_HEARTBEAT_SECONDS)
            if not _renew(context):
                owner_task.cancel()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        _monitor_failed(context)
        owner_task.cancel()


def _monitor_failed(context: RunContext) -> None:
    context.failed = True
    try:
        _terminal(context, context.repository.fail_run, cancel_on_conflict=True)
    except Exception:
        context.lost = True


def _renew(context: RunContext) -> bool:
    row = None
    if context.worker_id:
        row = context.repository.renew_run_owner(context.run.id, context.worker_id)
        if row is None:
            context.lost = True
            return False
    if not _reader_accessible(context):
        _revoke_reader(context)
        return False
    _stop_if_requested(context, row)
    return _renew_lease(context)


def _stop_if_requested(context: RunContext, row: dict | None) -> None:
    if row and row.get("cancelRequestedAt") and context.token:
        context.token.cancel()


def _renew_lease(context: RunContext) -> bool:
    if not context.lease:
        return True
    try:
        context.lease.renew()
    except AIQuotaError:
        context.failed = True
        return False
    return True


def _finalize(context: RunContext) -> None:
    try:
        if context.lost:
            return
        status = _stream_status(context)
        if status == "completed":
            _complete(context)
        elif status == "cancelled":
            _terminal(context, context.repository.cancel_run, assistant=_partial_assistant(context))
        else:
            artifacts = [item for item in context.deps.proposed_artifacts
                         if item.kind == "range" and not item.annotation_id] if context.deps else []
            _terminal(context, context.repository.fail_run, cancel_on_conflict=True,
                      assistant=_partial_assistant(context, frozenset(item.id for item in artifacts)),
                      error=_failure_message(context), artifacts=artifacts)
    except Exception:
        _monitor_failed(context)
    finally:
        _release_lease(context)


def _complete(context: RunContext) -> None:
    if context.result is None:
        _terminal(context, context.repository.fail_run)
        return
    artifacts = context.deps.proposed_artifacts if context.deps else []
    reader = context.reader and not context.review
    if not context.repository.complete_run(
        context.run.id, _assistant_message(context, context.result), context.worker_id,
        resources=_run_resources(_assistant_parts_of(context), context.bounds,
                                 context.reader, context.review),
        reader_case_id=context.case["id"] if reader else None,
        reader_version_id=context.case.get("versionId") if reader else None,
        review_case_id=context.case["id"] if context.review else None,
        artifacts=artifacts,
        write_record=context.deps.write_record if context.deps else None,
    ):
        context.lost = True


def _review_accessible(context: RunContext) -> bool:
    """审核运行实时重验：撤审、降权/停用或基线越过即撤销，不再产生新输出。"""
    deps_user = context.deps.user if context.deps else None
    user_id = deps_user["id"] if deps_user else context.run.user_id
    return (
        review_delivery_allowed(context.repository.database, context.case["id"], user_id)
        and review_baseline_current(context.repository.database, context.run.id)
    )


def _reader_accessible(context: RunContext) -> bool:
    if context.review:
        return _review_accessible(context)
    return not context.reader or version_readable_by_id(
        context.repository.database, context.case["id"], context.case.get("versionId")
    )


def _revoke_reader(context: RunContext) -> None:
    context.cancelled = True
    if context.token:
        context.token.cancel()


def _terminal(context: RunContext, finish, cancel_on_conflict=False, assistant=None, error=None,
              artifacts=None) -> None:
    kwargs = {"assistant": assistant} if assistant is not None else {}
    if error is not None:
        kwargs["error"] = error
    if artifacts:
        kwargs["artifacts"] = artifacts
    if not finish(context.run.id, context.worker_id, **kwargs):
        kwargs.pop("error", None)
        if kwargs.pop("artifacts", None):
            kwargs["assistant"] = _partial_assistant(context)
        if cancel_on_conflict and context.repository.cancel_run(
                context.run.id, context.worker_id, **kwargs):
            context.cancelled = True
        else:
            context.lost = True


def _release_lease(context: RunContext) -> None:
    if context.lease and not context.lease_released:
        context.lease_released = True
        context.lease.release()


def _projected_parts(row: AgentMessage, project) -> list[dict]:
    if row.role != "assistant":
        return row.parts
    return project(row.parts)


def load_history(repository: AgentRepository, thread: AgentThread, max_seq=None, *,
                 project) -> list:
    """模型历史与读取面共用同一来源权限投影，防止收紧后旧来源复述。"""
    rows = repository.messages(thread.id)
    rows = [row for row in rows if max_seq is None or row.message_seq <= max_seq]
    messages = [
        UIMessage.model_validate(_ui_message(row, project)) for row in rows
    ]
    return VercelAIAdapter.load_messages(messages)


def _ui_message(row: AgentMessage, project) -> dict:
    return {
        "id": row.id, "role": row.role, "metadata": row.metadata,
        "parts": _projected_parts(row, project),
    }
