"""真实模型 Thinking 的官方协议接入。

核对结论（阿里云百炼《深度思考模型的用法》官方文档，2026-09 核对）：
- qwen-plus 自 2025-04-28 快照起、qwen-flash 自 2025-07-28 快照起为混合
  思考模式且默认不开启思考，必须显式传参才会返回推理内容；
- 请求参数 ``enable_thinking`` 非 OpenAI 标准参数，需经 extra_body 下发，
  仅对官方明确列出的混合思考型号发送，不预判未来命名；
- 思考内容经响应 ``reasoning_content`` 字段返回，回复在 ``content`` 字段；
  商业版同时支持流式与非流式输出（仅部分开源版仅支持流式），本应用固定
  使用流式；
- 多轮对话历史只回传 content，不回传 reasoning_content，回传会报错；
  该历史协议仅适用于本文档列出的思考模型，不覆盖其他 provider 的通用
  历史语义。

型号边界说明：
- 仅收录官方文档当前列出的商业版型号；开源版与 Kimi/DeepSeek/GLM/
  MiniMax 等其他厂商部署使用不同参数，未收录；
- qwen-turbo 官方仅确认别名及其后快照、未列起始日期，日期快照一律不
  启用（宁可少展示思考，也不误发参数）。

依据：https://help.aliyun.com/zh/model-studio/deep-thinking
"""

from __future__ import annotations

import re

from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.profiles.openai import OpenAIModelProfile

# 仅思考模式：始终思考，无需也不得依赖 enable_thinking，但同样返回
# reasoning_content 并适用同一历史协议。
_THINKING_ONLY = frozenset({
    "qwq-plus", "qwen3.7-max-preview", "qwen3.7-max-2026-05-17", "qwen3.8-2.4t-a95b",
})

# 混合思考模式：enable_thinking 可开关思考。qwen-plus/flash 快照自
# 2025-04-28 / 2025-07-28 起支持，其余为官方明确列出的型号。
_HYBRID_MODELS = frozenset({
    "qwen-plus", "qwen-plus-latest", "qwen-flash", "qwen-flash-latest",
    "qwen-turbo", "qwen-turbo-latest",
    "qwen3-max", "qwen3-max-preview", "qwen3-max-2026-01-23",
    "qwen3.5-plus", "qwen3.5-plus-2026-02-15",
    "qwen3.5-flash", "qwen3.5-flash-2026-02-23",
    "qwen3.6-max-preview", "qwen3.6-plus", "qwen3.6-plus-2026-04-02",
    "qwen3.6-flash", "qwen3.6-flash-2026-04-16",
    "qwen3.7-max", "qwen3.7-max-2026-05-20", "qwen3.7-max-2026-06-08",
    "qwen3.7-plus", "qwen3.7-plus-2026-05-26",
    "qwen3.7-flash", "qwen3.7-flash-2026-07-15",
    "qwen3.8-max", "qwen3.8-max-0902", "qwen3.8-flash",
})

# 日期快照下界：官方文档明确 qwen-plus 自 2025-04-28、qwen-flash 自
# 2025-07-28 起为混合思考；更早快照（如 qwen-plus-2025-01-25）不支持。
# qwen-turbo 无官方起始日期，不在其中，即日期快照一律不启用。
_SNAPSHOT = re.compile(r"^(qwen-(?:plus|flash|turbo))-(\d{4})-(\d{2})-(\d{2})$")
_SNAPSHOT_FLOORS = {"qwen-plus": (2025, 4, 28), "qwen-flash": (2025, 7, 28)}

# 官方多轮协议：思考模型历史消息不回传 reasoning_content。
thinking_history_profile = OpenAIModelProfile(openai_chat_send_back_thinking_parts=False)


def _hybrid_snapshot(model: str) -> bool:
    match = _SNAPSHOT.match(model)
    floor = _SNAPSHOT_FLOORS.get(match.group(1)) if match else None
    if floor is None:
        return False
    return tuple(int(part) for part in match.groups()[1:]) >= floor


def official_thinking_model(model: str) -> bool:
    """是否官方文档列出的思考模型（适用 reasoning_content 历史协议）。"""
    name = model.strip()
    return name in _THINKING_ONLY or name in _HYBRID_MODELS or _hybrid_snapshot(name)


def thinking_settings(model: str) -> OpenAIChatModelSettings | None:
    """混合思考模型按官方参数开启思考；其余模型返回 None，不发送该参数。"""
    if model.strip() not in _HYBRID_MODELS and not _hybrid_snapshot(model):
        return None
    return OpenAIChatModelSettings(extra_body={"enable_thinking": True})
