"""活动 Run 的共享 UI chunk 流与终态消息恢复。"""

from __future__ import annotations

import asyncio
import json
import os

from starlette.responses import StreamingResponse

from app.modules.agent.models import AgentThread, AgentThreadEvent
from app.modules.agent.repository import AgentRepository
from app.modules.agent.visibility import SourceGate

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


class RunStream:
    """保存官方 Adapter 输出；首次连接和跨 worker 重连读取同一份流。"""

    def __init__(self, repository, run, deps) -> None:
        self.repository, self.run, self.deps = repository, run, deps

    async def publish(self, chunk) -> None:
        encoded = chunk.encode(6)
        if encoded == "[DONE]":
            return
        refs = [ref.model_dump(by_alias=True, mode="json")
                for ref in [*self.deps.hits, *self.deps.evidence]] if self.deps else []
        await asyncio.to_thread(
            self.repository.database.agent_run_streams.update_one,
            {"_id": self.run.id},
            {"$push": {"chunks": json.loads(encoded)}, "$set": {"sources": refs}},
            upsert=True,
        )


async def run_stream(repository, run_id, case_id, user, access_check, project):
    index = 0
    while True:
        if access_check and not access_check():
            return
        run = repository.database.agent_runs.find_one({"id": run_id}, {"stream": 0})
        if not run:
            return
        row = repository.database.agent_run_streams.find_one(
            {"_id": run_id}, {"chunks": {"$slice": [index, 200]}, "sources": 1},
        ) or {}
        gate = SourceGate(repository.database, user, case_id)
        readable = all(gate.readable(ref) for ref in row.get("sources", []))
        chunks = row.get("chunks", [])
        if readable:
            body = "".join(
                sse_data(chunk) for chunk in chunks
                if chunk["type"] not in {"finish", "error", "abort"}
            )
            if body:
                yield body
        index += len(chunks)
        if run["status"] != "active" and len(chunks) < 200:
            for chunk in _run_terminal_chunks(repository, run, project):
                yield sse_data(chunk)
            yield sse_data("[DONE]")
            return
        await asyncio.sleep(STREAM_POLL_SECONDS)


def _run_terminal_chunks(repository, run, project):
    message = repository.message(run["threadId"], run["assistantMessageId"])
    if message:
        yield {"type": "data-agent-message", "transient": True, "data":
               message.model_copy(update={"parts": project(message.parts)}).model_dump(
                   by_alias=True, mode="json")}
    if run["status"] == "failed":
        yield {"type": "error", "errorText": run.get("error") or "AI 服务暂不可用"}
    else:
        yield TERMINAL_CHUNKS[f"run.{run['status']}"]


def live_response(repository, run_id, case_id, user, access_check, project):
    return StreamingResponse(
        run_stream(repository, run_id, case_id, user, access_check, project),
        media_type="text/event-stream", headers=sse_headers(),
    )


def _fail_chunk(event: AgentThreadEvent) -> dict:
    return {
        "type": "error",
        "errorText": str(event.payload.get("error") or "AI 服务暂不可用"),
    }


def _message_chunks(
    repository: AgentRepository, event: AgentThreadEvent, project,
) -> list[dict]:
    message = repository.message(event.thread_id, str(event.payload.get("messageId")))
    if message is None or message.role != "assistant":
        return []
    visible = message.model_copy(update={"parts": project(message.parts)})
    return [{
        "type": "data-agent-message",
        "data": visible.model_dump(by_alias=True, mode="json"),
        "transient": True,
    }]


def _event_chunks(repository: AgentRepository, event: AgentThreadEvent, project) -> list[dict]:
    if event.event_type == "message.created":
        return _message_chunks(repository, event, project)
    if event.event_type == "run.failed":
        return [_fail_chunk(event)]
    if event.event_type in TERMINAL_CHUNKS:
        return [TERMINAL_CHUNKS[event.event_type]]
    return []


async def events_stream(
    repository: AgentRepository, thread: AgentThread, after_seq: int,
    access_check=None, *, project,
):
    """按 Thread 游标重放增量，无活动 Run 且无未读事件后以 [DONE] 收尾。"""
    cursor = after_seq
    while True:
        if access_check and not access_check():
            return
        for event in repository.events_after(thread.id, cursor):
            if access_check and not access_check():
                return
            cursor = event.event_seq
            for chunk in _event_chunks(repository, event, project):
                yield sse_data(chunk)
        if _stream_finished(repository, thread, cursor):
            yield sse_data("[DONE]")
            return
        await asyncio.sleep(STREAM_POLL_SECONDS)


def _stream_finished(repository: AgentRepository, thread: AgentThread, cursor: int) -> bool:
    current = repository.thread_by_id(thread.id)
    return current is None or current.active_run_id is None and cursor >= current.event_seq
