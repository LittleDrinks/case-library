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


async def propose_revision(
    ctx: RunContext[ToolDeps], paragraph_index: int, replacement: str, reason: str = ""
) -> dict:
    """只为当前 baseRevision 的一个段落创建 pending Artifact，正文不变。"""
    try:
        artifact = _propose(ctx, paragraph_index, replacement, reason)
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    return _artifact_view(artifact)


def _propose(ctx: RunContext[ToolDeps], paragraph_index: int, replacement: str, reason: str):
    return artifacts.propose_artifact(
        ctx.deps.database, ctx.deps.case_id, ctx.deps.thread_id, ctx.deps.run_id,
        paragraph_index, replacement, reason, list(ctx.deps.sources),
    )


def _artifact_view(artifact) -> dict:
    return {
        "artifactId": artifact.id,
        "paragraphIndex": artifact.target.paragraph_index,
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
