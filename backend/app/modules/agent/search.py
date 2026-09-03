"""Agent 检索领域服务：调用现有权限过滤检索服务并服务端重建 SourceRef。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.tools import RunContext

from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import SourceRef
from app.modules.search.meilisearch import SearchUnavailable
from app.modules.search.models import SearchQuery
from app.modules.search.service import CatalogSearch, search_catalog

MAX_SOURCES = 3
SNIPPET_CHARACTERS = 120


@dataclass(slots=True)
class CorpusResult:
    sources: list[SourceRef]


def _snippet(item: dict) -> str:
    text = str(item.get("summary") or item.get("title") or "")
    return text[:SNIPPET_CHARACTERS]


def source_ref(item: dict) -> SourceRef:
    """从检索服务实际返回的条目重建来源引用，忽略模型提供的任何出处。"""
    return SourceRef(
        kind=item["kind"], id=str(item["id"]), title=str(item.get("title") or ""),
        snippet=_snippet(item),
    )


def search_platform(deps: ToolDeps, query: str) -> CorpusResult:
    """按当前用户权限检索平台资料，返回服务端构造的固定 SourceRef。"""
    search = CatalogSearch(
        SearchQuery(q=query[:200], page_size=MAX_SOURCES), deps.user, deps.secret_path
    )
    try:
        response = search_catalog(deps.database, deps.catalog, deps.catalog_state, search)
    except SearchUnavailable as error:
        raise RuntimeError("检索服务暂不可用") from error
    return CorpusResult([source_ref(item) for item in response["items"][:MAX_SOURCES]])


async def search_corpus(ctx: RunContext[ToolDeps], query: str) -> dict:
    """模型可见的 search_corpus 工具：结果记录到本次 Run 的服务端状态。"""
    result = search_platform(ctx.deps, query)
    ctx.deps.sources = result.sources
    return {"sources": [item.model_dump(by_alias=True) for item in result.sources]}
