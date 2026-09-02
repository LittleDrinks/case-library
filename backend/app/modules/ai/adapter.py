from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import HTTPException, Request
from pydantic import ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart

from app.modules.agent.streaming import ClosableStreamingResponse
from app.modules.ai.provider import open_model


async def from_request(request: Request, agent, message_id: str | None = None):
    try:
        return await VercelAIAdapter.from_request(
            request, agent=agent, sdk_version=6, server_message_id=message_id,
            manage_system_prompt="server", allow_uploaded_files=False,
        )
    except (ValidationError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="AI 消息格式无效") from error


def latest_text(adapter: VercelAIAdapter) -> str:
    messages = adapter.run_input.messages
    if adapter.run_input.trigger != "submit-message" or not messages:
        raise HTTPException(status_code=422, detail="只支持发送新消息")
    latest = messages[-1]
    if latest.role != "user" or any(not isinstance(part, TextUIPart) for part in latest.parts):
        raise HTTPException(status_code=422, detail="消息必须是普通文本")
    text = "".join(part.text for part in latest.parts).strip()
    if not text or len(text) > 20_000:
        raise HTTPException(status_code=422, detail="消息内容无效")
    return text


@asynccontextmanager
async def selected_model(selection, settings):
    if not selection:
        yield None
        return
    async with open_model(selection, settings.app_environment == "test") as model:
        yield model


async def stream_adapter(adapter, selection, settings, instructions, lease):
    try:
        async with selected_model(selection, settings) as model:
            async for chunk in adapter.run_stream(model=model, instructions=instructions):
                yield chunk
    finally:
        if lease:
            lease.release()


def streaming_response(adapter, stream):
    return ClosableStreamingResponse(adapter.streaming_response(stream), stream)
