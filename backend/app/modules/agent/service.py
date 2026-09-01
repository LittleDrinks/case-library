from __future__ import annotations

import asyncio
import os
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.modules.agent.models import AgentMessage, AgentRun, AgentThread, TerminalRunStatus
from app.modules.agent.repository import AgentRepository
from app.modules.agent.runtime import case_instructions
from app.modules.ai.provider import open_model
from app.modules.ai.quota import AIQuotaError


RUN_HEARTBEAT_SECONDS = float(os.getenv("AGENT_RUN_HEARTBEAT_SECONDS", "5"))


@dataclass(slots=True)
class RunContext:
    repository: AgentRepository
    run: AgentRun
    adapter: VercelAIAdapter
    history: list
    prompt: str
    case: dict
    agent: object
    selection: object | None = None
    settings: object | None = None
    lease: object | None = None
    worker_id: str | None = None
    result: object | None = None
    cancelled: bool = False
    failed: bool = False
    lost: bool = False
    lease_released: bool = False


def _run_kwargs(context: RunContext, model=None) -> dict:
    values = {
        "message_history": context.history,
        "conversation_id": context.run.thread_id,
        "run_id": context.run.id,
        "instructions": case_instructions(context.case),
        "user_prompt": context.prompt,
    }
    if model is not None:
        values["model"] = model
    return values


async def _native_events(context: RunContext):
    try:
        async with _model_context(context) as model:
            async with context.agent.run_stream_events(**_run_kwargs(context, model)) as events:
                async for event in events:
                    yield event
    except RunCancelled:
        context.cancelled = True
        raise
    except asyncio.CancelledError:
        context.cancelled = True
        raise
    except Exception:
        context.failed = True
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
    return open_model(context.selection, allow_internal)


def _message_id(assistant_id: str, user_id: str):
    def generate(_message, role, _index):
        return assistant_id if role == "assistant" else user_id

    return generate


def _dump_messages(context: RunContext, result):
    return VercelAIAdapter.dump_messages(
        result.new_messages(),
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


def _assistant_message(context: RunContext, result) -> AgentMessage:
    assistant = next((item for item in _dump_messages(context, result) if item.role == "assistant"), None)
    if assistant is None:
        raise RuntimeError("AI 响应为空")
    return AgentMessage(
        id=assistant.id, thread_id=context.run.thread_id, run_id=context.run.id,
        role="assistant", metadata=assistant.metadata, parts=_assistant_parts(assistant),
        created_at=datetime.now(UTC),
    )


async def _on_complete(context: RunContext, result) -> None:
    context.result = result


async def _on_cancel(context: RunContext, _cancelled) -> None:
    context.cancelled = True


def _adapter_stream(context: RunContext):
    return context.adapter.transform_stream(
        _native_events(context),
        on_complete=lambda result: _on_complete(context, result),
        on_cancel=lambda cancelled: _on_cancel(context, cancelled),
    )


async def protocol_stream(context: RunContext):
    monitor = asyncio.create_task(_monitor(context, asyncio.current_task()))
    try:
        async with aclosing(_adapter_stream(context)) as stream:
            async for chunk in stream:
                yield chunk
    except (RunCancelled, asyncio.CancelledError):
        context.cancelled = True
        raise
    except (BrokenPipeError, ConnectionResetError, GeneratorExit) as error:
        context.cancelled = True
        raise asyncio.CancelledError from error
    except Exception:
        context.failed = True
        raise
    finally:
        monitor.cancel()
        _finalize(context)


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
        if not context.repository.fail_run(context.run.id, context.worker_id):
            context.lost = True
    except Exception:
        context.lost = True


def _renew(context: RunContext) -> bool:
    if context.worker_id and not context.repository.renew_run_owner(
        context.run.id, context.worker_id
    ):
        context.lost = True
        return False
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
            _terminal(context, context.repository.cancel_run)
        else:
            _terminal(context, context.repository.fail_run)
    except Exception:
        _monitor_failed(context)
    finally:
        _release_lease(context)


def _complete(context: RunContext) -> None:
    if context.result is None:
        _terminal(context, context.repository.fail_run)
        return
    if not context.repository.complete_run(
        context.run.id, _assistant_message(context, context.result), context.worker_id
    ):
        context.lost = True


def _terminal(context: RunContext, finish) -> None:
    if not finish(context.run.id, context.worker_id):
        context.lost = True


def _release_lease(context: RunContext) -> None:
    if context.lease and not context.lease_released:
        context.lease_released = True
        context.lease.release()


def load_history(repository: AgentRepository, thread: AgentThread) -> list:
    rows = repository.messages(thread.id)
    return VercelAIAdapter.load_messages(
        [UIMessage.model_validate(_ui_message(row)) for row in rows]
    )


def _ui_message(row: AgentMessage) -> dict:
    return {"id": row.id, "role": row.role, "metadata": row.metadata, "parts": row.parts}
