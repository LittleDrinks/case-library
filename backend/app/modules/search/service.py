from __future__ import annotations

from app.modules.cases.service import CaseError
from app.modules.search.cursor import decode_cursor, encode_cursor, scope_key
from app.modules.search.meilisearch import (
    CatalogRequest,
    MountedFilter,
    Principal,
    SearchUnavailable,
)
from app.modules.search.state import CatalogSnapshot

MAX_SEARCH_ATTEMPTS = 3


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


def _stable_search(state, catalog, create_request, before: CatalogSnapshot):
    for _attempt in range(MAX_SEARCH_ATTEMPTS):
        page = catalog.search(create_request(before.revoked_keys))
        after = state.read()
        if after.target != before.target:
            break
        if before.same_version(after):
            return page
        before = after
    raise SearchUnavailable("检索目录正在同步")


def _request(query, kind, target, page_size, state, filters, user, mounted, revoked):
    return CatalogRequest(
        q=query.strip(),
        kind=kind,
        generation=target.generation,
        index_uid=target.index_uid,
        index_epoch=target.index_epoch,
        page_size=page_size,
        offset=state.offset,
        filters=filters,
        principal=_principal(user),
        mounted_filter=mounted,
        excluded_keys=revoked,
        include_metadata=state.page == 1,
    )


def _cursor(enabled, page, offset, scope, secret_path):
    return encode_cursor(page, offset, scope, secret_path) if enabled else None


def _response(query, kind, page_size, state, page, scope, secret_path) -> dict:
    metadata = page.metadata if state.page == 1 else None
    return {
        "query": query.strip(),
        "kind": kind,
        "page": state.page,
        "pageSize": page_size,
        "items": page.items,
        **_metadata_response(metadata),
        **_cursor_response(page, state, page_size, scope, secret_path),
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


def _cursor_response(page, state, page_size, scope, secret_path) -> dict:
    return {
        "nextCursor": _cursor(
            page.has_next, state.page + 1, state.offset + page_size, scope, secret_path
        ),
        "previousCursor": _cursor(
            page.has_previous,
            state.page - 1,
            max(0, state.offset - page_size),
            scope,
            secret_path,
        ),
    }


def _request_factory(query, kind, target, page_size, state, filters, user, mounted):
    def create_request(revoked):
        return _request(query, kind, target, page_size, state, filters, user, mounted, revoked)
    return create_request


def search_catalog(
    database, catalog, catalog_state, user, query,
    kind, cursor, page_size, filters, secret_path,
) -> dict:
    before = catalog_state.read()
    active, target = _clean_filters(filters or {}), before.target
    scope_filters = {**active, "mountedInCaseId": filters.get("mountedInCaseId")}
    scope = scope_key(query, kind, page_size, scope_filters, user, target.generation)
    cursor_state = decode_cursor(cursor, scope, secret_path)
    mounted = _mount_filter(database, user, filters.get("mountedInCaseId"))

    create_request = _request_factory(
        query, kind, target, page_size, cursor_state, active, user, mounted
    )
    page = _stable_search(catalog_state, catalog, create_request, before)
    return _response(query, kind, page_size, cursor_state, page, scope, secret_path)
