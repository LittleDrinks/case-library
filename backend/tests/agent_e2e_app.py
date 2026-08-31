from __future__ import annotations

from contextlib import ExitStack

from pydantic_ai.models.function import FunctionModel

from app.main import create_app
from app.modules.agent.runtime import agent


ANSWER = "隔离 FunctionModel 回答：已依据当前案例完成分析。"


async def _stream(_messages, _info):
    for character in ANSWER:
        yield character


def _overrides() -> ExitStack:
    stack = ExitStack()
    model = FunctionModel(stream_function=_stream, model_name="function-e2e")
    stack.enter_context(agent.override(model=model))
    return stack


_OVERRIDES = _overrides()
app = create_app()
