"""确定性 tracer 模型：FunctionModel 驱动生产 Agent 走完整修订链路。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Callable

from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.modules.agent.resources import CASE_EDIT_SKILL

SKILL_ID = CASE_EDIT_SKILL.id
SEARCH_QUERY = "科学家精神"
REPLACEMENT = "修订后的段落：教学目标、课堂任务与评价依据逐项对应，依据已检索平台资料。"
REASON = "对照检索资料明确评价依据，使段落主张可核验"


def _tool_calls(messages) -> list[str]:
    return [
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", [])
        if part.part_kind == "tool-call"
    ]


def _paragraph_index(messages) -> int:
    for message in messages:
        for part in getattr(message, "parts", []):
            if part.part_kind != "user-prompt":
                continue
            match = re.search(r"第(\d+)段", str(getattr(part, "content", "")))
            if match:
                return max(0, int(match.group(1)) - 1)
    return 0


def tracer_response(messages, _info=None) -> ModelResponse:
    """按已发生的工具调用推进：加载 Skill → 检索 → 提议 → 结束。"""
    called = _tool_calls(messages)
    if "load_capability" not in called:
        return ModelResponse(parts=[ToolCallPart(tool_name="load_capability", args={"id": SKILL_ID})])
    if "search_corpus" not in called:
        return ModelResponse(parts=[ToolCallPart(tool_name="search_corpus", args={"query": SEARCH_QUERY})])
    if "propose_revision" not in called:
        return ModelResponse(parts=[ToolCallPart(tool_name="propose_revision", args={
            "paragraph_index": _paragraph_index(messages),
            "replacement": REPLACEMENT,
            "reason": REASON,
        })])
    return ModelResponse(parts=[TextPart(content="已生成单段修订候选，等待作者决定。")])


async def _stream_deltas(response: ModelResponse) -> AsyncIterator[dict | str]:
    for index, part in enumerate(response.parts):
        if isinstance(part, TextPart):
            yield part.content
        elif isinstance(part, ToolCallPart):
            delta = DeltaToolCall(
                name=part.tool_name, json_args=json.dumps(part.args_as_dict()),
                tool_call_id=part.tool_call_id or f"tracer-{index}",
            )
            yield {0: delta}


def tracer_model(recorder: Callable | None = None) -> FunctionModel:
    """同一生产 Agent 使用的确定性模型装配，依次调用 Skill 加载、检索与提议。

    recorder 每次模型请求收到 (messages, info)，供测试断言消息与 instructions 通道。
    """

    async def stream(messages, info):
        if recorder:
            recorder(messages, info)
        async for delta in _stream_deltas(tracer_response(messages, info)):
            yield delta

    return FunctionModel(stream_function=stream)
