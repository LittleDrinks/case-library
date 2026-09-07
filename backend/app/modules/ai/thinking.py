"""真实模型 Thinking 的官方协议接入。

核对结论（阿里云百炼 OpenAI 兼容协议，《深度思考模型的用法》官方文档）：
- qwen-plus、qwen-turbo、qwen-flash 及 qwen3-max、qwen3.5+ 商业版为混合思考
  模式，其中 qwen-plus 系列默认不开启思考，必须显式传参才会返回推理内容；
- 请求参数 ``enable_thinking`` 非 OpenAI 标准参数，需经 extra_body 下发；
- 思考内容经响应 ``reasoning_content`` 字段返回，回复在 ``content`` 字段；
- 多轮对话历史只回传 content，不回传 reasoning_content（官方多轮对话示例
  明确要求忽略该字段，回传会导致 400）。

模型不支持或未返回思考时不下发该参数、不合成任何思考内容，前端仅展示
provider 真实返回的 reasoning。
依据：https://help.aliyun.com/zh/model-studio/deep-thinking
"""

from __future__ import annotations

import re

from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.profiles.openai import OpenAIModelProfile

# 官方文档列出的商业版混合思考模型命名：qwen-plus / qwen-turbo / qwen-flash
# 全系（含 latest 与日期快照），以及 qwen3-max 与 qwen3.5 起 max/plus/flash
# 系列。日期快照以官方支持列表为准（qwen-plus 自 2025-04-28 起为混合思考）。
_HYBRID_THINKING = re.compile(
    r"^(qwen-(?:plus|turbo|flash)|qwen-?3(?:\.\d+)?-(?:max|plus|flash))"
)

# 官方多轮协议：历史消息不回传 reasoning_content，对返回该字段的模型一律禁用。
thinking_history_profile = OpenAIModelProfile(openai_chat_send_back_thinking_parts=False)


def thinking_settings(model: str) -> OpenAIChatModelSettings | None:
    """混合思考模型按官方参数开启思考；其余模型返回 None，不发送该参数。"""
    if not _HYBRID_THINKING.match(model.strip()):
        return None
    return OpenAIChatModelSettings(extra_body={"enable_thinking": True})
