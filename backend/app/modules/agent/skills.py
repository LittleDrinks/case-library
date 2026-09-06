"""Run 能力装配：领域工具常驻，Skill 只补充任务指令与资源读取。

平台领域工具（检索、标签目录、读源、提议修订）始终可用，与是否选择
Skill 无关；管理员发布的 Skill 通过 bound_skill_capability 按需加载
正文与资源，不新增工具权限。只读 Run 不注册写工具。
"""

from __future__ import annotations

import hashlib

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext, Tool

from app.modules.agent import artifacts
from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import SourceRef
from app.modules.agent.search import list_tag_catalog, search_corpus
from app.modules.agent.source_reader import read_source as read_domain_source
from app.modules.cases.service import CaseError
from app.modules.skills.service import BoundSkill, SkillError

DOMAIN_CAPABILITY_ID = "platform-tools"


async def read_source(ctx: RunContext[ToolDeps], source_type: str, source_id: str) -> dict:
    """读取资料区来源或本次检索命中的真实内容。

    source_type 取 case/material/attachment/knowledge；按当前身份验权并
    固定已批准版本。状态 ok 之外的 no_access、empty、unavailable、error
    都不含正文内容。
    """
    result = read_domain_source(
        ctx.deps.database, ctx.deps.store, ctx.deps.user, ctx.deps.case_id,
        source_type, source_id, ctx.deps.case_version_id,
    )
    if result.get("status") == "ok":
        _record_evidence(ctx.deps, SourceRef.model_validate(result["source"]))
    return result


def _record_evidence(deps: ToolDeps, ref) -> None:
    """只记录实际读到的证据：固定版本与定位，重复读取不重复记录。"""
    if not any(item.identity() == ref.identity() for item in deps.evidence):
        deps.evidence.append(ref)


async def propose_revision(
    ctx: RunContext[ToolDeps], paragraph_index: int, replacement: str, reason: str = ""
) -> dict:
    """只为当前 baseRevision 的一个段落创建 pending Artifact，正文不变。

    引用只关联本次 Run 实际读过的来源证据；未读过时 sources 为空。
    """
    try:
        artifact = _propose(ctx, paragraph_index, replacement, reason)
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    return _artifact_view(artifact)


def _propose(ctx: RunContext[ToolDeps], paragraph_index: int, replacement: str, reason: str):
    return artifacts.propose_artifact(
        ctx.deps.database, ctx.deps.case_id, ctx.deps.thread_id, ctx.deps.run_id,
        paragraph_index, replacement, reason, list(ctx.deps.evidence), ctx.deps.user,
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


def domain_tools(write_enabled: bool) -> list[Tool]:
    """常驻领域工具：读与检索始终可用，写工具只在可写 Run 注册。"""
    tools = [search_corpus, list_tag_catalog, read_source]
    if write_enabled:
        tools.append(propose_revision)
    return tools


def domain_capability(instructions: str, write_enabled: bool) -> Capability:
    """平台领域能力：不延迟加载，工具与资料区指令对每次 Run 直接可见。"""
    return Capability(
        id=DOMAIN_CAPABILITY_ID, instructions=instructions,
        tools=domain_tools(write_enabled),
    )


def bound_skill_capability(bound: BoundSkill) -> Capability:
    """已发布 Skill 的延迟加载能力：描述进目录，正文与资源加载后可见。"""
    return Capability(
        id=bound.skill_id,
        description=bound.description,
        instructions=skill_instructions(bound),
        tools=[resource_tool(bound)],
        defer_loading=True,
    )


def skill_instructions(bound: BoundSkill) -> str:
    """SKILL.md 正文 + 资源清单；资源按需经读取工具获取，不预载进上下文。"""
    listing = "\n".join(f"- `{file.path}`" for file in bound.files)
    tool = resource_tool_name(bound)
    return (
        f"{bound.body}\n\n## 资源文件（按需用工具 {tool} 读取，不要凭记忆改写）\n{listing}"
    )


def resource_tool(bound: BoundSkill) -> Tool:
    """读取工具闭包绑定 Run 开始时解析的版本快照，发布变化不影响本次运行。"""
    name = resource_tool_name(bound)

    async def read_resource(ctx: RunContext[ToolDeps], path: str) -> dict:
        """读取当前已加载 Skill 的资源文件。path 必须是资源清单中的相对路径。"""
        try:
            content = bound.read_resource(path)
        except SkillError as error:
            raise ModelRetry(f"{error.detail}；可用路径见资源清单") from error
        return {"path": path, "content": content}

    return Tool(read_resource, name=name)


def resource_tool_name(bound: BoundSkill) -> str:
    suffix = hashlib.sha256(bound.skill_id.encode("utf-8")).hexdigest()[:8]
    return f"read_skill_resource_{suffix}"
