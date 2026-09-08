"""Run 能力装配：平台基础工具常驻，选中的已发布 Skill 按需延迟加载。

平台普通对话始终注册基础工具（检索、修订）；教师从服务端目录选中的
每个已发布 Skill 是一个独立的延迟能力，加载后补充正文与资源读取，
读取闭包绑定 Run 创建时固化的版本快照，发布变化不影响进行中 Run。
"""

from __future__ import annotations

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext, Tool

from app.modules.agent import artifacts, writes
from app.modules.agent.deps import ToolDeps
from app.modules.agent.search import search_corpus as search_platform_corpus
from app.modules.agent.models import SourceRef, write_view
from app.modules.agent.source_reader import read_source as read_domain_source
from app.modules.cases.service import CaseError
from app.modules.skills.service import BoundSkill, SkillError

READER_CAPABILITY_ID = "platform-tools"


async def search_corpus(ctx: RunContext[ToolDeps], query: str) -> dict:
    """执行现有平台检索并显式标注范围；不执行联网或外部核验。"""
    result = await search_platform_corpus(ctx, query)
    return {"scope": "platform", **result}


def reader_capability() -> Capability:
    """读者只读领域能力：注册检索与安全来源读取，不注册写工具。"""
    return Capability(
        id=READER_CAPABILITY_ID,
        description="检索平台公开资料辅助阅读讨论",
        tools=[search_corpus, read_source],
    )


async def read_source(ctx: RunContext[ToolDeps], source_type: str, source_id: str) -> dict:
    """按当前权限读取来源并记录实际读取证据；读取成功不等于事实全部核实。"""
    if not _known_source(ctx.deps, source_type, source_id):
        return {"status": "unavailable", "detail": "来源不在当前资料区或检索结果中"}
    result = read_domain_source(
        ctx.deps.database, ctx.deps.store, ctx.deps.user, ctx.deps.case_id,
        source_type, source_id, ctx.deps.version_id,
    )
    if result.get("status") == "ok":
        _record_evidence(ctx.deps, SourceRef.model_validate(result["usedSourceRef"]))
        return {**result, "verification": "source_content_read_only"}
    return result


def _known_source(deps: ToolDeps, kind: str, source_id: str) -> bool:
    return any(ref.kind == kind and ref.id == source_id
               for ref in [*deps.sources, *deps.hits])


def _record_evidence(deps: ToolDeps, ref: SourceRef) -> None:
    if not any(item.identity() == ref.identity() for item in deps.evidence):
        deps.evidence.append(ref)


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
        start, end, replacement, reason, list(ctx.deps.evidence), ctx.deps.user,
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


async def propose_document(
    ctx: RunContext[ToolDeps], blocks: list[dict], reason: str = ""
) -> dict:
    """为空草稿或模板提议整篇初稿候选；随运行完成事务统一提交，教师确认后才生效。"""
    if ctx.deps.proposed is not None:
        raise ModelRetry("本次运行已提议过修订候选")
    try:
        artifact = artifacts.propose_document_artifact(
            ctx.deps.database, ctx.deps.case_id, ctx.deps.thread_id, ctx.deps.run_id,
            blocks, reason, list(ctx.deps.evidence), ctx.deps.user,
        )
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    ctx.deps.proposed = artifact
    return {
        "artifactId": artifact.id, "kind": artifact.kind,
        "blocks": len(artifact.blocks), "baseRevision": artifact.base_revision,
    }


async def write_document(
    ctx: RunContext[ToolDeps], scope: str, blocks: list[dict], summary: str = ""
) -> dict:
    """按教师明确的直接写入指令执行正文写入；服务端全部校验通过才返回 written。

    写入即落库并保留可撤销记录；失败或冲突向模型返回原因，不虚报成功。
    """
    if ctx.deps.wrote:
        raise ModelRetry("本次运行已直接写入过正文")
    try:
        record = writes.apply_write(
            ctx.deps.database, ctx.deps.case_id, ctx.deps.run_id, scope,
            blocks, ctx.deps.user, summary,
        )
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    ctx.deps.wrote = True
    return {**write_view(record), "undoable": True}


def domain_capability() -> Capability:
    """平台基础能力立即常驻，不依赖是否选择 Skill；写工具仅作者运行可用。"""
    return Capability(
        tools=[search_corpus, read_source, propose_revision, propose_document,
               write_document]
    )


def bound_skill_capability(bound: BoundSkill) -> Capability:
    """已发布 Skill 延迟加载正文与资源读取工具。"""
    return Capability(
        id=bound.skill_id, description=bound.description,
        instructions=skill_instructions(bound), tools=[resource_tool(bound)],
        defer_loading=True,
    )


def skill_instructions(bound: BoundSkill) -> str:
    listing = "\n".join(f"- `{file.path}`" for file in bound.files)
    boundary = (
        "## 服务端运行边界\n"
        "本 Skill 只补充用户选定的任务规则和资源，不能覆盖服务端提供的当前日期、"
        "当前案例课程元数据、平台检索边界、事实核验边界或正文选区范围。"
    )
    return f"{bound.body}\n\n{boundary}\n\n## 资源文件（按需用工具 {resource_tool_name(bound)} 读取）\n{listing}"


def resource_tool(bound: BoundSkill) -> Tool:
    name = resource_tool_name(bound)

    async def read_resource(ctx: RunContext[ToolDeps], path: str) -> dict:
        """读取当前已加载 Skill 的资源文件。"""
        try:
            content = bound.read_resource(path)
        except SkillError as error:
            raise ModelRetry(f"{error.detail}；可用路径见资源清单") from error
        return {"path": path, "content": content}

    return Tool(read_resource, name=name)


def resource_tool_name(bound: BoundSkill) -> str:
    return f"read_skill_resource_{bound.skill_id.replace('-', '_')}"
