from __future__ import annotations

import asyncio
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel

from app.main import create_app


ANSWER = "隔离 FunctionModel 回答：已依据当前案例完成分析。"


async def _stream(_messages, _info):
    if "并发" in str(_messages):
        await asyncio.sleep(0.25)
    for character in ANSWER:
        yield character


def _application():
    application = create_app()
    model = FunctionModel(stream_function=_stream, model_name="function-e2e")
    application.state.agent = Agent(
        model=model, output_type=str, name="case-library-agent-e2e"
    )
    return application


app = _application()
