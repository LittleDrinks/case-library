"""Agent 平台检索领域工具：复用既有权限过滤目录服务，不另建索引或回查。

暴露真实标签目录、嵌套标签条件、结果规模与游标翻页；来源引用一律由
服务端从目录返回条目重建，模型输出不能伪造出处。
"""

from __future__ import annotations

from pydantic import ValidationError
from pydantic_ai.tools import RunContext

from app.modules.agent.case_area import dedupe_refs, ref_view
from app.modules.agent.deps import ToolDeps
from app.modules.agent.models import SourceRef
from app.modules.cases.service import CaseError
from app.modules.search.meilisearch import SearchUnavailable
from app.modules.search.models import SearchRequest
from app.modules.search.service import CatalogSearch, search_catalog
from app.modules.tags.service import list_groups

DEFAULT_PAGE_SIZE = 5
MAX_PAGE_SIZE = 20
SNIPPET_CHARACTERS = 120


def source_ref(item: dict) -> SourceRef:
    """从检索服务实际返回的条目重建来源引用，忽略模型提供的任何出处。"""
    kind, item_id = str(item["kind"]), str(item["id"])
    return SourceRef(
        kind=kind, id=item_id, title=str(item.get("title") or ""),
        snippet=str(item.get("summary") or "")[:SNIPPET_CHARACTERS],
        locator=f"{kind}:{item_id}",
    )


def _agent_query(query: str, kind: str, tag_condition: dict | None,
                 page_size: int, cursor: str | None) -> SearchRequest:
    return SearchRequest(
        q=query[:200], kind=kind, tagExpression=tag_condition,
        pageSize=max(1, min(int(page_size), MAX_PAGE_SIZE)), cursor=cursor,
    )


def search_platform(deps: ToolDeps, query: str, kind: str = "all",
                    tag_condition: dict | None = None,
                    page_size: int = DEFAULT_PAGE_SIZE,
                    cursor: str | None = None) -> dict:
    """按当前用户权限检索平台目录，返回服务端重建的结果与翻页游标。"""
    try:
        parsed = _agent_query(query, kind, tag_condition, page_size, cursor)
        response = search_catalog(
            deps.database, deps.catalog, deps.catalog_state,
            CatalogSearch(parsed, deps.user, deps.secret_path),
        )
    except ValidationError as error:
        return {"status": "error", "detail": f"检索参数无效：{error.error_count()} 处"}
    except CaseError as error:
        return {"status": "error", "detail": str(error.detail)}
    except SearchUnavailable as error:
        return {"status": "unavailable", "detail": f"检索目录暂不可用：{error}"}
    return _search_response(deps, parsed, response)


def _search_response(deps: ToolDeps, query: SearchRequest, response: dict) -> dict:
    refs = [source_ref(item) for item in response["items"]]
    _record_hits(deps, refs)
    return {
        "status": "ok",
        "query": response["query"],
        "kind": response["kind"],
        "tagCondition": response.get("tagCondition"),
        "total": response.get("total"),
        "page": response["page"],
        "pageSize": response["pageSize"],
        "sources": [ref_view(ref) for ref in refs],
        "nextCursor": response.get("nextCursor"),
        "previousCursor": response.get("previousCursor"),
    }


def _record_hits(deps: ToolDeps, refs: list[SourceRef]) -> None:
    """命中来源累计记录、按类型+ID 去重；不覆盖资料区选择。"""
    deps.hits = dedupe_refs([*deps.hits, *refs])


async def search_corpus(ctx: RunContext[ToolDeps], query: str,
                        kind: str = "all", tag_condition: dict | None = None,
                        page_size: int = DEFAULT_PAGE_SIZE,
                        cursor: str | None = None) -> dict:
    """按当前用户权限检索平台已发布案例、知识与素材。

    tag_condition 使用嵌套结构：{"op": "and"|"or", "children": [{"tagId": "..."}]}，
    标签 ID 来自 list_tag_catalog；返回 total（仅第一页）与 nextCursor，可翻页。
    """
    return search_platform(ctx.deps, query, kind, tag_condition, page_size, cursor)


async def list_tag_catalog(ctx: RunContext[ToolDeps]) -> dict:
    """返回管理员维护的真实标签目录（组与标签），供结构化条件引用。"""
    return {"status": "ok", "groups": list_groups(ctx.deps.database)}
