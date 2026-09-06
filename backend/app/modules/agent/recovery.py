"""Run 流的两个输出面：活动请求的进程内 tee 缓冲与恢复请求的事件尾 SSE。"""

from __future__ import annotations

import asyncio
import json
import os

from starlette.responses import StreamingResponse

from app.modules.agent.models import AgentThread, AgentThreadEvent
from app.modules.agent.repository import AgentRepository

STREAM_POLL_SECONDS = float(os.getenv("AGENT_STREAM_POLL_SECONDS", "0.1"))

TERMINAL_CHUNKS = {
    "run.completed": {"type": "finish", "finishReason": "stop"},
    "run.cancelled": {"type": "abort", "reason": "运行已取消"},
}


def sse_headers() -> dict[str, str]:
    return {
        "x-vercel-ai-ui-message-stream": "v1",
        "cache-control": "no-cache",
        "connection": "keep-alive",
    }


def sse_data(payload) -> str:
    body = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
    return f"data: {body}\n\n"


class LiveBuffer:
    """活动 Run 的 UI chunk 缓冲；订阅者断开不影响执行任务。"""

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._done = False
        self._changed = asyncio.Condition()

    async def publish(self, chunk) -> None:
        encoded = chunk.encode(6)
        if encoded == "[DONE]":
            return
        async with self._changed:
            self._chunks.append(encoded)
            self._changed.notify_all()

    async def close(self) -> None:
        async with self._changed:
            self._done = True
            self._changed.notify_all()

    async def stream(self):
        index = 0
        while True:
            async with self._changed:
                while index >= len(self._chunks) and not self._done:
                    await self._changed.wait()
                batch, done = self._chunks[index:], self._done
            for chunk in batch:
                yield sse_data(chunk)
            index += len(batch)
            if done:
                yield sse_data("[DONE]")
                return


def live_response(buffer: LiveBuffer) -> StreamingResponse:
    return StreamingResponse(
        buffer.stream(), media_type="text/event-stream", headers=sse_headers()
    )


def _fail_chunk(event: AgentThreadEvent) -> dict:
    return {
        "type": "error",
        "errorText": str(event.payload.get("error") or "AI 服务暂不可用"),
    }


def _text_chunks(part: dict) -> list[dict]:
    part_id = str(part.get("id") or "text")
    return [
        {"type": "text-start", "id": part_id},
        {"type": "text-delta", "id": part_id, "delta": str(part.get("text") or "")},
        {"type": "text-end", "id": part_id},
    ]


def _tool_chunks(part: dict, index: int) -> list[dict]:
    part_id = str(part.get("toolCallId") or f"tool-{index}")
    name = str(part["type"])[len("tool-"):]
    return [
        {"type": "tool-input-start", "toolCallId": part_id, "toolName": name},
        {
            "type": "tool-input-available",
            "toolCallId": part_id,
            "toolName": name,
            "input": part.get("input") or {},
        },
        {
            "type": "tool-output-available",
            "toolCallId": part_id,
            "output": part.get("output"),
        },
    ]


def _message_chunks(repository: AgentRepository, event: AgentThreadEvent) -> list[dict]:
    message = repository.message(event.thread_id, str(event.payload.get("messageId")))
    if message is None or message.role != "assistant":
        return []
    chunks = [{"type": "start", "messageId": message.id}]
    for index, part in enumerate(message.parts):
        kind = str(part.get("type") or "")
        if kind == "text":
            chunks.extend(_text_chunks(part))
        elif kind.startswith("tool-"):
            chunks.extend(_tool_chunks(part, index))
    return chunks


def _event_chunks(repository: AgentRepository, event: AgentThreadEvent) -> list[dict]:
    if event.event_type == "message.created":
        return _message_chunks(repository, event)
    if event.event_type == "run.failed":
        return [_fail_chunk(event)]
    if event.event_type in TERMINAL_CHUNKS:
        return [TERMINAL_CHUNKS[event.event_type]]
    return []


async def events_stream(
    repository: AgentRepository, thread: AgentThread, after_seq: int
):
    """按 Thread 游标重放增量，无活动 Run 且无未读事件后以 [DONE] 收尾。"""
    cursor = after_seq
    while True:
        for event in repository.events_after(thread.id, cursor):
            cursor = event.event_seq
            for chunk in _event_chunks(repository, event):
                yield sse_data(chunk)
        current = repository.thread_by_id(thread.id)
        if current is None or (
            current.active_run_id is None and cursor >= current.event_seq
        ):
            yield sse_data("[DONE]")
            return
        await asyncio.sleep(STREAM_POLL_SECONDS)
