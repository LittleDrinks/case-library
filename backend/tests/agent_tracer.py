"""确定性 tracer 模型：FunctionModel 驱动生产 Agent 走检索-修订链路。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

from pydantic_ai import ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models.function import DeltaThinkingPart, DeltaToolCall, FunctionModel

from tests.skill_packages import EXAMPLE_PATH, SKILL_ID

SEARCH_QUERY = "科学家精神"
SUMMARY_MARKER = "摘要测试"
TRACER_PARAGRAPHS = ("第一段保持原样。", "第二段：教学目标需要更明确的评价依据。")
# Native Tiptap/ProseMirror positions for the second paragraph: 11..30.
TRACER_SELECTION = (11, 30)
REPLACEMENT = "修订后的段落：教学目标、课堂任务与评价依据逐项对应，依据已检索平台资料。"
REASON = "对照检索资料明确评价依据，使段落主张可核验"
RESOURCE_TOOL = f"read_skill_resource_{SKILL_ID.replace('-', '_')}"
# 侧栏浏览器验收：带标记的提问首轮同时流出慢速 ThinkingPart 与既有工具调用。
THINKING_MARKER = "思考测试"
THINKING_TEXT = "先核对资料区与选区，再检索平台依据。"


def _tool_calls(messages) -> list[str]:
    return [
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", [])
        if part.part_kind == "tool-call"
    ]


def _wants_thinking(messages) -> bool:
    """仅看最近一条用户输入（user-prompt），忽略工具返回等其他 part。"""
    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            if getattr(part, "part_kind", "") == "user-prompt":
                return THINKING_MARKER in part.content
    return False


def thinking_pieces(content: str) -> list[str]:
    half = max(1, len(content) // 2)
    return [content[:half], content[half:]]


def _load_capability_response(messages, skill_id) -> ModelResponse:
    """首轮加载 Skill；带思考标记时同一响应内先流出慢速 ThinkingPart。"""
    parts: list = []
    if _wants_thinking(messages):
        parts.append(ThinkingPart(content=THINKING_TEXT))
    parts.append(ToolCallPart(tool_name="load_capability", args={"id": skill_id}))
    return ModelResponse(parts=parts)


def _tool_response(name: str, args: dict) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])


def _summary_query(messages) -> str:
    """摘要验收：带标记时从提问《》内提取唯一标题作检索词；默认检索词不变。"""
    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            prompt = getattr(part, "content", "")
            if getattr(part, "part_kind", "") == "user-prompt" and SUMMARY_MARKER in prompt:
                return prompt.split("《", 1)[1].split("》", 1)[0]
    return SEARCH_QUERY


def _search_source(messages) -> dict:
    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            if part.part_kind != "tool-return" or part.tool_name != "search_corpus":
                continue
            sources = part.content["sources"]
            source = next((item for item in sources if item["kind"] == "case"), None)
            if source is None:
                raise AssertionError("tracer requires a searchable case source")
            return {"source_type": source["kind"], "source_id": source["id"]}
    raise AssertionError("tracer requires a completed search before reading")


def tracer_response(messages, _info=None, skill_id: str | None = None,
                    selection: tuple[int, int] | None = None) -> ModelResponse:
    """按已发生的工具调用推进：加载 Skill → 检索 → 读源 → 提议。"""
    called = _tool_calls(messages)
    if skill_id and "load_capability" not in called:
        return _load_capability_response(messages, skill_id)
    if skill_id and RESOURCE_TOOL not in called:
        return _tool_response(RESOURCE_TOOL, {"path": EXAMPLE_PATH})
    if "search_corpus" not in called:
        return _tool_response("search_corpus", {"query": _summary_query(messages)})
    if "read_source" not in called:
        return _tool_response("read_source", _search_source(messages))
    if "propose_revision" not in called:
        start, end = selection or TRACER_SELECTION
        return _tool_response("propose_revision", {
            "start": start, "end": end, "replacement": REPLACEMENT, "reason": REASON,
        })
    return ModelResponse(parts=[TextPart(content="已生成单段修订候选，等待作者决定。")])


async def _stream_deltas(response: ModelResponse) -> AsyncIterator[dict | str]:
    for index, part in enumerate(response.parts):
        if isinstance(part, TextPart):
            yield part.content
        elif isinstance(part, ThinkingPart):
            for piece in thinking_pieces(part.content):
                yield {0: DeltaThinkingPart(content=piece)}
                await asyncio.sleep(0.8)
        elif isinstance(part, ToolCallPart):
            delta = DeltaToolCall(
                name=part.tool_name, json_args=json.dumps(part.args_as_dict()),
                tool_call_id=part.tool_call_id or f"tracer-{index}",
            )
            yield {0: delta}


def tracer_model(recorder: Callable | None = None, skill_id: str | None = None,
                 selection: tuple[int, int] | None = None) -> FunctionModel:
    """同一生产 Agent 使用的确定性模型装配，依次调用 Skill 加载、检索与提议。

    recorder 每次模型请求收到 (messages, info)，供测试断言消息与 instructions 通道。
    """

    async def stream(messages, info):
        if recorder:
            recorder(messages, info)
        async for delta in _stream_deltas(
            tracer_response(messages, info, skill_id, selection)
        ):
            yield delta

    return FunctionModel(stream_function=stream)
