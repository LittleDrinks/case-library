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
TRACER_FIRST_SELECTION = (1, 9)
REPLACEMENT = "修订后的段落：教学目标、课堂任务与评价依据逐项对应，依据已检索平台资料。"
SECOND_REPLACEMENT = "第二轮修订：教学目标、课堂任务与评价依据逐项对应，并补充可核验的课堂证据。"
REASON = "对照检索资料明确评价依据，使段落主张可核验"
SECOND_REASON = "根据第一轮候选继续收紧表述，补充可核验的课堂证据"
RESOURCE_TOOL = f"read_skill_resource_{SKILL_ID.replace('-', '_')}"
# 侧栏浏览器验收：带标记的提问首轮同时流出慢速 ThinkingPart 与既有工具调用。
THINKING_MARKER = "思考测试"
THINKING_TEXT = "先核对资料区与选区，再检索平台依据。"
PROVIDER_FAILURE_MARKER = "确定性上游故障"
SLOW_ROUND_MARKER = "确定性 A 慢速"


def _tool_calls(messages) -> list[str]:
    start = max(
        (index for index, message in enumerate(messages)
         if any(getattr(part, "part_kind", "") == "user-prompt" for part in message.parts)
         and not any(getattr(part, "part_kind", "") == "tool-return" for part in message.parts)),
        default=0,
    )
    return [
        part.tool_name
        for message in messages[start:]
        for part in getattr(message, "parts", [])
        if part.part_kind == "tool-call"
    ]


def _latest_prompt(messages) -> str:
    for message in reversed(messages):
        for part in getattr(message, "parts", []):
            if getattr(part, "part_kind", "") == "user-prompt":
                return part.content
    return ""


def _wants_thinking(messages) -> bool:
    return THINKING_MARKER in _latest_prompt(messages)


def _has_previous_proposal(messages) -> bool:
    return any(
        getattr(part, "tool_name", "") == "propose_revision"
        for message in messages for part in getattr(message, "parts", [])
    )


def _record_proposal(round_state: dict, response: ModelResponse) -> None:
    if any(getattr(part, "tool_name", "") == "propose_revision" for part in response.parts):
        round_state["proposal_seen"] = True


async def _prepare_marked_stream(messages, state: dict) -> bool:
    prompt = _latest_prompt(messages)
    round_prompt = "" if prompt.startswith("<system>") else prompt
    task = asyncio.current_task()
    detected = "第二轮" in prompt or _has_previous_proposal(messages)
    round_state = state["rounds"].get(task)
    if round_state is None or (round_prompt and round_prompt != round_state["prompt"]):
        round_state = {"prompt": round_prompt, "second": detected, "proposal_seen": False}
        state["rounds"][task] = round_state
    elif detected:
        round_state["second"] = True
    second_round = round_state["second"]
    if PROVIDER_FAILURE_MARKER in prompt and not state["failure_consumed"]:
        state["failure_consumed"] = True
        raise RuntimeError("deterministic provider failure")
    if SLOW_ROUND_MARKER in prompt and not state["slow_consumed"]:
        state["slow_consumed"] = True
        await asyncio.sleep(45)
    return second_round


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


def _proposal_response(messages, selection, second_round) -> ModelResponse:
    if second_round is None:
        second_round = "第二轮" in _latest_prompt(messages)
    new_annotation = second_round and not _has_previous_proposal(messages)
    start, end = TRACER_FIRST_SELECTION if new_annotation else (selection or TRACER_SELECTION)
    return _tool_response("propose_revision", {
        "start": start, "end": end,
        "replacement": SECOND_REPLACEMENT if second_round else REPLACEMENT,
        "reason": SECOND_REASON if second_round else REASON,
    })


def tracer_response(messages, _info=None, skill_id: str | None = None,
                    selection: tuple[int, int] | None = None,
                    second_round: bool | None = None,
                    force_proposal: bool = False) -> ModelResponse:
    """按已发生的工具调用推进：加载 Skill → 检索 → 读源 → 提议。"""
    called = _tool_calls(messages)
    if force_proposal:
        called = [name for name in called if name != "propose_revision"]
    if skill_id and "load_capability" not in called:
        return _load_capability_response(messages, skill_id)
    if skill_id and RESOURCE_TOOL not in called:
        return _tool_response(RESOURCE_TOOL, {"path": EXAMPLE_PATH})
    if "search_corpus" not in called:
        return _tool_response("search_corpus", {"query": _summary_query(messages)})
    if "read_source" not in called:
        return _tool_response("read_source", _search_source(messages))
    if "propose_revision" not in called:
        return _proposal_response(messages, selection, second_round)
    return ModelResponse(parts=[TextPart(content="已生成单段修订候选，等待作者决定。")])


async def _stream_deltas(response: ModelResponse) -> AsyncIterator[dict | str]:
    for index, part in enumerate(response.parts):
        if isinstance(part, TextPart):
            yield part.content
        elif isinstance(part, ThinkingPart):
            for piece in thinking_pieces(part.content):
                yield {index: DeltaThinkingPart(content=piece)}
                await asyncio.sleep(0.8)
        elif isinstance(part, ToolCallPart):
            delta = DeltaToolCall(
                name=part.tool_name, json_args=json.dumps(part.args_as_dict()),
                tool_call_id=part.tool_call_id or f"tracer-{index}",
            )
            yield {index: delta}


def tracer_model(recorder: Callable | None = None, skill_id: str | None = None,
                 selection: tuple[int, int] | None = None) -> FunctionModel:
    """同一生产 Agent 使用的确定性模型装配，依次调用 Skill 加载、检索与提议。

    recorder 每次模型请求收到 (messages, info)，供测试断言消息与 instructions 通道。
    """

    state = {"failure_consumed": False, "slow_consumed": False, "rounds": {}}

    async def stream(messages, info):
        second_round = await _prepare_marked_stream(messages, state)
        round_state = state["rounds"][asyncio.current_task()]
        if recorder:
            recorder(messages, info)
        response = tracer_response(
            messages, info, skill_id, selection, second_round, not round_state["proposal_seen"]
        )
        _record_proposal(round_state, response)
        async for delta in _stream_deltas(
            response
        ):
            yield delta

    return FunctionModel(stream_function=stream)
