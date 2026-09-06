"""通用 Skill 运行时：已发布版本按需加载，资源经绑定清单按需读取。

平台 Skill（case-edit-skill）保持原有路径；管理员发布的 Skill 通过
bound_skill_capability 接入同一 defer_loading 机制，不新增工具权限。
"""

from __future__ import annotations

import hashlib

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext, Tool

from app.modules.agent import artifacts
from app.modules.agent.deps import ToolDeps
from app.modules.agent.resources import CASE_EDIT_SKILL
from app.modules.agent.search import search_corpus
from app.modules.cases.service import CaseError
from app.modules.skills.service import BoundSkill, SkillError

SKILL_ID = CASE_EDIT_SKILL.id


async def propose_revision(
    ctx: RunContext[ToolDeps], paragraph_index: int, replacement: str, reason: str = ""
) -> dict:
    """只为当前 baseRevision 的一个段落创建 pending Artifact，正文不变；仅作者草稿上下文注册。"""
    try:
        artifact = _propose(ctx, paragraph_index, replacement, reason)
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    return _artifact_view(artifact)


def _propose(ctx: RunContext[ToolDeps], paragraph_index: int, replacement: str, reason: str):
    return artifacts.propose_artifact(
        ctx.deps.database, ctx.deps.case_id, ctx.deps.thread_id, ctx.deps.run_id,
        paragraph_index, replacement, reason, list(ctx.deps.sources), ctx.deps.user,
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


READER_CAPABILITY_ID = "case-reading"


def reader_capability() -> Capability:
    """读者上下文的固定只读能力：仅平台检索，不暴露任何案例写工具。"""
    return Capability(
        id=READER_CAPABILITY_ID,
        description="检索平台公开资料辅助案例讨论",
        tools=[search_corpus],
    )


def case_edit_skill() -> Capability:
    """固定版本 Skill：初始只暴露名称与描述，load_capability 后正文与工具可用。"""
    return Capability(
        id=SKILL_ID,
        description="围绕目标段落检索平台资料，产出一条可核验的单段修订候选",
        defer_loading=True,
        instructions=CASE_EDIT_SKILL.read(),
        tools=[search_corpus, propose_revision],
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
