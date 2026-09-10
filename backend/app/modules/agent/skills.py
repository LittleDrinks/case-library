"""Run 能力装配：平台基础工具常驻，选中的已发布 Skill 按需延迟加载。

平台普通对话始终注册基础工具（检索、修订）；教师从服务端目录选中的
每个已发布 Skill 是一个独立的延迟能力，加载后补充正文与资源读取，
读取闭包绑定 Run 创建时固化的版本快照，发布变化不影响进行中 Run。
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext, Tool

from app.modules.agent import artifacts, writes
from app.modules.agent.blocks import DraftBlocks
from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import SourceRef, write_view
from app.modules.agent.search import CorpusSearchParams
from app.modules.agent.search import search_corpus as search_platform_corpus
from app.modules.agent.source_reader import read_source as read_domain_source
from app.modules.cases.service import CaseError
from app.modules.skills.service import BoundSkill, SkillError

READER_CAPABILITY_ID = "platform-tools"
_GENERATION_ACTION = re.compile(
    r"(?:生成|重写|改写|撰写|编写|起草|创作|重做|写|整理|修改|generate|rewrite|redraft|write)"
    r".{0,16}(?:全文|全篇|整篇|整份|全案|整案|初稿|完整(?:的|地)?(?:案例|文档|稿|正文|文章)?|整个(?:案例|文档|稿|正文|文章)|full\s+(?:draft|document))",
    re.IGNORECASE,
)
_FULL_GENERATION_PHRASE = re.compile(r"完整生成|full\s+(?:draft|document)", re.IGNORECASE)
_GENERATION_QUESTIONS = ("吗", "呢", "请问", "是否", "能不能", "可否", "能否", "如何", "怎么", "怎样")
_GENERATION_CONDITIONALS = ("如果", "假如", "假设", "若是", "要是", "一旦", "的话")
_GENERATION_NEGATIONS = ("不要", "不必", "不需要", "不用", "无需", "无须", "请勿", "勿", "不想", "不希望", "没有", "没", "未", "不是")
_GENERATION_MENTION_PREFIXES = ("引用", "提及", "说明", "解释", "介绍", "分析", "讨论", "理解", "查看", "显示")
_GENERATION_MENTION_SUFFIX = re.compile(
    r"^\s*(?:的)?(?:功能|按钮|规则|模式|选项|机制|说明|意思|含义|用法|结果|内容)"
)
_GENERATION_PARTIAL = re.compile(
    r"(?:中的|里的|之中|内部)|^\s*的(?:第|某|部分|片段|选区|段|节|[一二三四五六七八九十\d])"
)
_NEGATED_BARE = re.compile(r"(?:^|[请你我他它们])(?:不|别).{0,16}$")


def full_generation_requested(prompt: str) -> bool:
    requested = False
    for clause in writes.message_clauses((prompt or "").lower(), split_discourse=True):
        if _generation_context_blocked(clause):
            continue
        for match in _generation_matches(clause):
            if _generation_match_negated(clause, match):
                requested = False
            elif not _generation_match_blocked(clause, match):
                requested = True
    return requested


def _generation_matches(clause: str):
    yield from _GENERATION_ACTION.finditer(clause)
    yield from _FULL_GENERATION_PHRASE.finditer(clause)


def _generation_context_blocked(clause: str) -> bool:
    return any(token in clause for token in _GENERATION_QUESTIONS + _GENERATION_CONDITIONALS)


def _generation_match_blocked(clause: str, match: re.Match) -> bool:
    before = clause[max(0, match.start() - 24):match.start()]
    after = clause[match.end():match.end() + 16]
    return _generation_match_negated(clause, match) or _generation_mentioned(before, after) or bool(
        _GENERATION_PARTIAL.search(match.group()) or _GENERATION_PARTIAL.search(after)
    )


def _generation_match_negated(clause: str, match: re.Match) -> bool:
    before = clause[max(0, match.start() - 24):match.start()]
    return _generation_negated(before)


def _generation_negated(before: str) -> bool:
    if any(marker in before for marker in _GENERATION_NEGATIONS):
        return True
    return _NEGATED_BARE.search(before.strip()) is not None


def _generation_mentioned(before: str, after: str) -> bool:
    return any(before.rstrip().endswith(prefix) for prefix in _GENERATION_MENTION_PREFIXES) or bool(
        _GENERATION_MENTION_SUFFIX.match(after)
    )


async def search_corpus(ctx: RunContext[ToolDeps], params: CorpusSearchParams) -> dict:
    """站内检索平台公开案例/知识/素材，不是联网检索或外部核验。

    先不带 query 调用可发现真实标签目录与命中规模；筛选用返回的真实标签
    ID，翻页把上一页 nextCursor 原样传入 cursor；引用前用 read_source 读源。
    """
    result = await search_platform_corpus(ctx, params)
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
    ctx: RunContext[ToolDeps], blocks: DraftBlocks, reason: str = ""
) -> dict:
    """暂存整篇 AI 生成稿；运行成功后才落为只读版本。"""
    if not ctx.deps.full_generation_allowed:
        raise ModelRetry("本条消息未请求完整生成，不能创建 AI 版本")
    if ctx.deps.proposed is not None:
        raise ModelRetry("本次运行已提议过修订候选")
    return _propose_document(ctx, blocks, reason)


def _propose_document(ctx: RunContext[ToolDeps], blocks: DraftBlocks, reason: str) -> dict:
    try:
        artifact = artifacts.propose_document_artifact(
            ctx.deps.database, ctx.deps.case_id, ctx.deps.thread_id, ctx.deps.run_id,
            blocks, reason, list(ctx.deps.evidence), ctx.deps.user,
        )
    except CaseError as error:
        raise ModelRetry(str(error.detail)) from error
    ctx.deps.proposed = artifact
    return {
        "kind": artifact.kind, "status": "pending",
        "blocks": len(artifact.blocks), "baseRevision": artifact.base_revision,
    }


async def write_document(
    ctx: RunContext[ToolDeps], scope: Literal["document", "selection"],
    blocks: DraftBlocks, summary: str = "",
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
    ctx.deps.write_record = record
    return {**write_view(record), "undoable": True}


def domain_capability() -> Capability:
    """平台基础能力立即常驻，不依赖是否选择 Skill；写工具仅作者运行可用。"""
    return Capability(
        tools=[search_corpus, read_source, propose_revision, propose_document,
               write_document]
    )


def bound_skill_capability(bound: BoundSkill, *, defer_loading: bool = True) -> Capability:
    """绑定已发布 Skill；显式审核调用立即加载规则，资源仍按需读取。"""
    return Capability(
        id=bound.skill_id, description=bound.description,
        instructions=skill_instructions(bound), tools=[resource_tool(bound)],
        defer_loading=defer_loading,
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
