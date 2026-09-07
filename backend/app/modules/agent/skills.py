"""Skill v2.1 运行时：Pydantic AI deferred capability 按需加载正文与工具。"""

from __future__ import annotations

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext

from app.modules.agent import artifacts
from app.modules.agent.deps import ToolDeps
from app.modules.agent.resources import CASE_EDIT_SKILL
from app.modules.agent.search import search_corpus
from app.modules.cases.service import CaseError

SKILL_ID = CASE_EDIT_SKILL.id
READER_CAPABILITY_ID = "platform-tools"


def reader_capability() -> Capability:
    """读者只读领域能力：仅注册检索工具，不注册任何写工具。"""
    return Capability(
        id=READER_CAPABILITY_ID,
        description="检索平台公开资料辅助阅读讨论",
        tools=[search_corpus],
    )


async def propose_revision(
    ctx: RunContext[ToolDeps], start: int, end: int, replacement: str, reason: str = ""
) -> dict:
    """为教师选定的正文范围构建修订候选；随运行完成事务统一提交。"""
    if ctx.deps.proposed is not None:
        raise ModelRetry("本次运行已提议过修订候选")
    try:
        artifact = _propose(ctx, start, end, replacement, reason)
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    ctx.deps.proposed = artifact
    return _artifact_view(artifact)


def _propose(ctx: RunContext[ToolDeps], start: int, end: int, replacement: str, reason: str):
    return artifacts.propose_artifact(
        ctx.deps.database, ctx.deps.case_id, ctx.deps.thread_id, ctx.deps.run_id,
        start, end, replacement, reason, list(ctx.deps.sources), ctx.deps.user,
    )


def _artifact_view(artifact) -> dict:
    return {
        "artifactId": artifact.id,
        "from": artifact.target.from_pos,
        "to": artifact.target.to_pos,
        "quote": artifact.target.quote,
        "replacement": artifact.replacement,
        "reason": artifact.reason,
        "sources": [item.model_dump(by_alias=True) for item in artifact.sources],
        "baseRevision": artifact.base_revision,
    }


def case_edit_skill() -> Capability:
    """固定版本 Skill：初始只暴露名称与描述，load_capability 后正文与工具可用。"""
    return Capability(
        id=SKILL_ID,
        description="围绕目标段落检索平台资料，产出一条可核验的单段修订候选",
        defer_loading=True,
        instructions=CASE_EDIT_SKILL.read(),
        tools=[search_corpus, propose_revision],
    )
