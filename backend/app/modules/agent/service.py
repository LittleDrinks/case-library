from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import UIMessage

from app.modules.agent.models import AgentMessage, AgentRun, AgentThread, TerminalRunStatus
from app.modules.agent.repository import AgentRepository
from app.modules.agent.runtime import case_instructions


@dataclass(slots=True)
class RunContext:
    repository: AgentRepository
    run: AgentRun
    adapter: VercelAIAdapter
    history: list
    prompt: str
    case: dict
    agent: object
    result: object | None = None
    cancelled: bool = False


def _run_kwargs(context: RunContext) -> dict:
    return {
        "message_history": context.history,
        "conversation_id": context.run.thread_id,
        "run_id": context.run.id,
        "instructions": case_instructions(context.case),
        "user_prompt": context.prompt,
    }


async def _native_events(context: RunContext):
    async with context.agent.run_stream_events(**_run_kwargs(context)) as events:
        async for event in events:
            yield event


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
    messages = _dump_messages(context, result)
    assistant = next((item for item in messages if item.role == "assistant"), None)
    if assistant is None:
        raise RuntimeError("AI 响应为空")
    return AgentMessage(
        id=assistant.id,
        thread_id=context.run.thread_id,
        run_id=context.run.id,
        role="assistant",
        metadata=assistant.metadata,
        parts=_assistant_parts(assistant),
        created_at=datetime.now(UTC),
    )


async def _on_complete(context: RunContext, result) -> None:
    context.result = result


async def _on_cancel(context: RunContext, _cancelled) -> None:
    context.cancelled = True


def _finalize(context: RunContext, status: TerminalRunStatus) -> None:
    if status == "completed":
        if context.result is None or not context.repository.complete_run(
            context.run.id, _assistant_message(context, context.result)
        ):
            raise RuntimeError("AI 运行已结束")
    elif status == "cancelled":
        context.repository.cancel_run(context.run.id)
    else:
        context.repository.fail_run(context.run.id)


def _stream_status(context: RunContext, natural: bool, failed: bool) -> TerminalRunStatus:
    if failed:
        return "failed"
    if not natural:
        return "cancelled"
    if context.result is not None:
        return "completed"
    if context.cancelled:
        return "cancelled"
    return "failed"


def _adapter_stream(context: RunContext):
    return context.adapter.transform_stream(
        _native_events(context),
        on_complete=lambda result: _on_complete(context, result),
        on_cancel=lambda cancelled: _on_cancel(context, cancelled),
    )


async def protocol_stream(context: RunContext):
    natural = False
    failed = False
    try:
        stream = _adapter_stream(context)
        async with aclosing(stream):
            async for chunk in stream:
                yield chunk
        natural = True
    except asyncio.CancelledError:
        raise
    except Exception:
        failed = True
        raise
    finally:
        _finalize(context, _stream_status(context, natural, failed))


def load_history(repository: AgentRepository, thread: AgentThread) -> list:
    rows = repository.messages(thread.id)
    return VercelAIAdapter.load_messages(
        [UIMessage.model_validate(_ui_message(row)) for row in rows]
    )


def _ui_message(row: AgentMessage) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "metadata": row.metadata,
        "parts": row.parts,
    }
