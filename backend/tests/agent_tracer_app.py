"""确定性 tracer 装配：生产 FastAPI + 生产 Agent + FunctionModel，供 tracer E2E 使用。"""

from __future__ import annotations

from app.main import create_app
from app.modules.agent.runtime import agent
from tests.agent_tracer import tracer_model

_model_override = agent.override(model=tracer_model())
_model_override.__enter__()

app = create_app()
