from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import ValidationError
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart

from app.modules.agent.streaming import ClosableStreamingResponse
from app.modules.ai.provider import open_model
from app.modules.search.models import SearchSummaryRequest

PROMPT_PATH = Path(__file__).parent / "prompts" / "summary.md"


async def build_adapter(request: Request, agent) -> VercelAIAdapter:
    try:
        return await VercelAIAdapter.from_request(
            request, agent=agent, sdk_version=6,
            manage_system_prompt="server", allow_uploaded_files=False,
        )
    except (ValidationError, ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="检索摘要消息格式无效") from error


def parse_summary_request(adapter: VercelAIAdapter) -> SearchSummaryRequest:
    raw = adapter.run_input.model_dump()
    try:
        values = {key: raw.get(key) for key in ("query", "items")}
        return SearchSummaryRequest.model_validate(values)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="检索摘要请求无效") from error


def latest_query(adapter: VercelAIAdapter) -> str:
    messages = adapter.run_input.messages
    if adapter.run_input.trigger != "submit-message" or not messages:
        raise HTTPException(status_code=422, detail="只支持发送新消息")
    latest = messages[-1]
    if latest.role != "user" or any(not isinstance(part, TextUIPart) for part in latest.parts):
        raise HTTPException(status_code=422, detail="消息必须是普通文本")
    query = "".join(part.text for part in latest.parts).strip()
    if not query or len(query) > 20_000:
        raise HTTPException(status_code=422, detail="消息内容无效")
    return query


def summary_instructions(body: SearchSummaryRequest) -> str:
    items = json.dumps(body.items, ensure_ascii=False, separators=(",", ":"))
    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    return f"{prompt}\n\n用户问题：{body.query}\n当前可见结果：\n{items}"


@asynccontextmanager
async def _selected_model(selection, settings):
    if not selection:
        yield None
        return
    async with open_model(selection, settings.app_environment == "test") as model:
        yield model


async def stream_summary(adapter, selection, settings, instructions, lease):
    try:
        async with _selected_model(selection, settings) as model:
            async for chunk in adapter.run_stream(model=model, instructions=instructions):
                yield chunk
    finally:
        if lease:
            lease.release()


def summary_response(adapter, stream):
    return ClosableStreamingResponse(adapter.streaming_response(stream), stream)
