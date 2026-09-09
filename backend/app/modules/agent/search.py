"""Agent 检索领域服务：接入现有权限过滤检索服务并服务端重建 SourceRef。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext

from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import SourceRef
from app.modules.cases.service import CaseError
from app.modules.search.meilisearch import SearchUnavailable
from app.modules.search.models import FilterValue, SearchRequest, TagExpression
from app.modules.search.service import CatalogSearch, search_catalog
from app.modules.tags.service import list_groups

SNIPPET_CHARACTERS = 120


class CorpusSearchParams(BaseModel):
    """search_corpus 工具参数：结构化条件由现有公共检索模型统一验证。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    query: str = Field(
        default="", max_length=200,
        description="关键词，可为空；留空调用用于发现标签目录和命中规模",
    )
    kind: Literal["all", "case", "knowledge", "material"] = Field(
        default="all", description="资源类型：全部/案例/知识/素材",
    )
    tag_ids: list[FilterValue] = Field(
        default_factory=list, max_length=20, alias="tagIds",
        description="真实标签 ID 列表，只能取自工具返回的 tagCatalog",
    )
    tag_mode: Literal["all", "any"] = Field(
        default="all", alias="tagMode",
        description="多个标签的组合方式：all=同时满足，any=任一满足",
    )
    tag_expression: TagExpression | None = Field(
        default=None, alias="tagExpression",
        description="嵌套混合标签条件（and/or），与 tagIds、非默认 tagMode 互斥",
    )
    cursor: str | None = Field(
        default=None, min_length=1, max_length=2_000,
        description="翻页游标：把上一页返回的 nextCursor 原样传入",
    )
    page_size: int = Field(
        default=5, ge=1, le=20, alias="pageSize", description="每页条数",
    )


@dataclass(slots=True)
class CorpusResult:
    sources: list[SourceRef]
    page: dict


def _snippet(item: dict) -> str:
    text = str(item.get("summary") or item.get("title") or "")
    return text[:SNIPPET_CHARACTERS]


def source_ref(item: dict) -> SourceRef:
    """从检索服务实际返回的条目重建来源引用，忽略模型提供的任何出处。"""
    kind = item["kind"]
    return SourceRef(
        kind=kind, id=str(item["id"]), title=str(item.get("title") or ""),
        snippet=_snippet(item),
    )


def _record_hits(deps: ToolDeps, refs: list[SourceRef]) -> None:
    for ref in refs:
        if not any(item.identity() == ref.identity() for item in deps.hits):
            deps.hits.append(ref)


def _search_request(params: CorpusSearchParams) -> SearchRequest:
    """复用公共检索请求模型验证结构化条件，未知字段已在参数层拒绝。"""
    return SearchRequest.model_validate({
        "q": params.query, "kind": params.kind, "tagIds": params.tag_ids,
        "tagMode": params.tag_mode, "tagExpression": params.tag_expression,
        "cursor": params.cursor, "pageSize": params.page_size,
    })


def search_platform(deps: ToolDeps, params: CorpusSearchParams) -> CorpusResult:
    """按当前用户权限调用现有检索服务，返回服务端构造的来源与结果页。"""
    search = CatalogSearch(_search_request(params), deps.user, deps.secret_path)
    try:
        response = search_catalog(deps.database, deps.catalog, deps.catalog_state, search)
    except SearchUnavailable as error:
        raise RuntimeError("检索服务暂不可用") from error
    return CorpusResult([source_ref(item) for item in response["items"]], response)


def tag_catalog(database) -> list[dict]:
    """当前真实标签目录：供模型取真实标签 ID 组合检索条件。"""
    return [
        {"id": tag["id"], "name": tag["name"], "group": group["name"]}
        for group in list_groups(database)
        for tag in group.get("tags", [])
    ]


def corpus_view(result: CorpusResult, database) -> dict:
    """模型可见的结果页视图：规模、分面、标签目录（仅首页）与分页游标。"""
    page = result.page
    view = {
        "query": page["query"], "kind": page["kind"], "page": page["page"],
        "pageSize": page["pageSize"],
        "nextCursor": page["nextCursor"], "previousCursor": page["previousCursor"],
    }
    if page.get("metadataIncluded"):
        view.update(
            total=page["total"], counts=page["counts"], facets=page["facets"],
            tagCatalog=tag_catalog(database),
        )
    return view


def _retry_detail(error: CaseError | ValidationError) -> str:
    if isinstance(error, CaseError):
        return error.detail
    issues = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()[:3]
    )
    return f"检索条件无效：{issues}"


async def search_corpus(ctx: RunContext[ToolDeps], params: CorpusSearchParams) -> dict:
    """模型可见的 search_corpus 工具：结构化条件直达检索服务并记录来源。"""
    try:
        result = search_platform(ctx.deps, params)
    except (CaseError, ValidationError) as error:
        raise ModelRetry(_retry_detail(error)) from error
    _record_hits(ctx.deps, result.sources)
    return {
        "sources": [
            item.model_dump(by_alias=True, exclude_none=True)
            for item in result.sources
        ],
        **corpus_view(result, ctx.deps.database),
    }
