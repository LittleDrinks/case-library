from __future__ import annotations

from dataclasses import dataclass

from app.modules.cases.service import CaseError
from app.modules.search.cursor import CursorState, decode_cursor, encode_cursor, scope_key
from app.modules.search.meilisearch import (
    CatalogRequest,
    MountedFilter,
    Principal,
    SearchUnavailable,
)
from app.modules.search.models import SearchQuery
from app.modules.search.outbox import CatalogTarget
from app.modules.search.state import CatalogSnapshot

MAX_SEARCH_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class CatalogSearch:
    query: SearchQuery
    user: dict | None
    secret_path: str


@dataclass(frozen=True, slots=True)
class _CatalogSearchPlan:
    search: CatalogSearch
    target: CatalogTarget
    cursor: CursorState
    filters: dict
    mounted_filter: MountedFilter | None
    scope: str

    def catalog_request(self, revoked) -> CatalogRequest:
        query = self.search.query
        return CatalogRequest(
            q=query.q.strip(),
            kind=query.kind,
            generation=self.target.generation,
            index_uid=self.target.index_uid,
            index_epoch=self.target.index_epoch,
            page_size=query.page_size,
            offset=self.cursor.offset,
            filters=self.filters,
            principal=_principal(self.search.user),
            mounted_filter=self.mounted_filter,
            excluded_keys=revoked,
            include_metadata=self.cursor.page == 1,
        )

    def cursor_token(self, enabled: bool, page: int, offset: int) -> str | None:
        if not enabled:
            return None
        return encode_cursor(page, offset, self.scope, self.search.secret_path)


def _clean_filters(filters: dict) -> dict:
    cleaned = {}
    for name, value in filters.items():
        if name == "mountedInCaseId":
            continue
        if isinstance(value, list):
            value = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
        if value:
            cleaned[name] = value
    return cleaned


def _principal(user: dict | None) -> Principal:
    if not user:
        return Principal(None, "anonymous")
    role = "admin" if user["role"] == "admin" else "user"
    return Principal(user["id"], role)


def _can_read(case: dict, user: dict) -> bool:
    return case.get("publicationStatus") == "public" or (
        user["role"] == "admin" or case.get("ownerId") == user["id"]
    )


def _mount_filter(database, user, case_id: str | None) -> MountedFilter | None:
    if not case_id:
        return None
    if not user:
        raise CaseError(401, "请先登录")
    case = database.cases.find_one({"id": case_id})
    if not case or not _can_read(case, user):
        raise CaseError(404, "案例不存在")
    if user["role"] == "admin" or case.get("ownerId") == user["id"]:
        return MountedFilter("workingCaseIds", case_id)
    version_id = case.get("publishedVersionId")
    return MountedFilter("publishedVersionIds", version_id or "missing")


def _stable_search(state, catalog, plan: _CatalogSearchPlan, before: CatalogSnapshot):
    for _attempt in range(MAX_SEARCH_ATTEMPTS):
        page = catalog.search(plan.catalog_request(before.revoked_keys))
        after = state.read()
        if after.target != before.target:
            break
        if before.same_version(after):
            return page
        before = after
    raise SearchUnavailable("检索目录正在同步")


def _scope(search: CatalogSearch, target: CatalogTarget, filters: dict) -> str:
    query = search.query
    scoped = {**filters, "mountedInCaseId": query.mounted_case_id}
    return scope_key(
        query.q,
        query.kind,
        query.page_size,
        scoped,
        search.user,
        target.generation,
    )


def _resolve_search(database, search: CatalogSearch, target: CatalogTarget):
    query = search.query
    filters = _clean_filters(query.filters())
    scope = _scope(search, target, filters)
    cursor = decode_cursor(query.cursor, scope, search.secret_path)
    mounted = _mount_filter(database, search.user, query.mounted_case_id)
    return _CatalogSearchPlan(search, target, cursor, filters, mounted, scope)


def _response(plan: _CatalogSearchPlan, page) -> dict:
    query = plan.search.query
    metadata = page.metadata if plan.cursor.page == 1 else None
    return {
        "query": query.q.strip(),
        "kind": query.kind,
        "page": plan.cursor.page,
        "pageSize": query.page_size,
        "items": page.items,
        **_metadata_response(metadata),
        **_cursor_response(page, plan),
    }


def _metadata_response(metadata) -> dict:
    if metadata is None:
        return {"total": None, "counts": None, "facets": None, "metadataIncluded": False}
    return {
        "total": metadata.total,
        "counts": metadata.counts,
        "facets": metadata.facets,
        "metadataIncluded": True,
    }


def _cursor_response(page, plan: _CatalogSearchPlan) -> dict:
    state = plan.cursor
    search = plan.search
    page_size = search.query.page_size
    return {
        "nextCursor": plan.cursor_token(
            page.has_next,
            state.page + 1,
            state.offset + page_size,
        ),
        "previousCursor": plan.cursor_token(
            page.has_previous,
            state.page - 1,
            max(0, state.offset - page_size),
        ),
    }


def search_catalog(database, catalog, catalog_state, search: CatalogSearch) -> dict:
    before = catalog_state.read()
    plan = _resolve_search(database, search, before.target)
    page = _stable_search(catalog_state, catalog, plan, before)
    return _response(plan, page)
