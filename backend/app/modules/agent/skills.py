"""Skill v2.1 运行时：Pydantic AI deferred capability 按需加载正文与工具。"""

from __future__ import annotations

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext

from app.modules.agent import artifacts
from app.modules.agent.deps import ToolDeps
from app.modules.agent.resources import CASE_EDIT_SKILL
from app.modules.agent.search import search_corpus
from app.modules.agent.models import SourceRef
from app.modules.agent.source_reader import read_source as read_domain_source
from app.modules.cases.service import CaseError

SKILL_ID = CASE_EDIT_SKILL.id


async def read_source(ctx: RunContext[ToolDeps], source_type: str, source_id: str) -> dict:
    """按当前权限读取资料区或本次检索命中的来源，并记录实际证据。"""
    if not _known_source(ctx.deps, source_type, source_id):
        return {"status": "unavailable", "detail": "来源不在当前资料区或检索结果中"}
    result = read_domain_source(
        ctx.deps.database, ctx.deps.store, ctx.deps.user, ctx.deps.case_id,
        source_type, source_id,
    )
    if result.get("status") == "ok":
        _record_evidence(ctx.deps, SourceRef.model_validate(result["usedSourceRef"]))
    return result


def _known_source(deps: ToolDeps, kind: str, source_id: str) -> bool:
    return any(ref.kind == kind and ref.id == source_id
               for ref in [*deps.sources, *deps.hits])


def _record_evidence(deps: ToolDeps, ref: SourceRef) -> None:
    if not any(item.identity() == ref.identity() for item in deps.evidence):
        deps.evidence.append(ref)


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
        paragraph_index, replacement, reason, list(ctx.deps.evidence),
    )


def _artifact_view(artifact) -> dict:
    return {
        "artifactId": artifact.id,
        "paragraphIndex": artifact.target.paragraph_index,
        "quote": artifact.target.quote,
        "replacement": artifact.replacement,
        "reason": artifact.reason,
        "sources": [item.model_dump(by_alias=True, exclude_none=True) for item in artifact.sources],
        "baseRevision": artifact.base_revision,
    }


def case_edit_skill() -> Capability:
    """固定版本 Skill：初始只暴露名称与描述，load_capability 后正文与工具可用。"""
    return Capability(
        id=SKILL_ID,
        description="围绕目标段落检索平台资料，产出一条可核验的单段修订候选",
        defer_loading=True,
        instructions=CASE_EDIT_SKILL.read(),
        tools=[search_corpus, read_source, propose_revision],
    )
