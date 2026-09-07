"""Run 能力装配：平台基础工具常驻，选中的已发布 Skill 按需延迟加载。

平台普通对话始终注册基础工具（检索、修订）；教师从服务端目录选中的
每个已发布 Skill 是一个独立的延迟能力，加载后补充正文与资源读取，
读取闭包绑定 Run 创建时固化的版本快照，发布变化不影响进行中 Run。
"""

from __future__ import annotations

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext, Tool

from app.modules.agent import artifacts
from app.modules.agent.deps import ToolDeps
from app.modules.agent.search import search_corpus
from app.modules.cases.service import CaseError
from app.modules.skills.service import BoundSkill, SkillError

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


def domain_capability() -> Capability:
    """平台基础能力：检索与修订工具立即常驻，不依赖是否选择 Skill。"""
    return Capability(tools=[search_corpus, propose_revision])


def bound_skill_capability(bound: BoundSkill) -> Capability:
    """已发布 Skill 的独立延迟能力：描述进目录，加载后正文与资源可用。"""
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
    return f"read_skill_resource_{bound.skill_id.replace('-', '_')}"
