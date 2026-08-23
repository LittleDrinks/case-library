from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest

from app.modules.search.client import CatalogHealth, SearchSnapshot
from app.modules.search.meilisearch import (
    CatalogKey,
    CatalogRequest,
    MeilisearchCatalog,
    Principal,
    SearchUnavailable,
)


class FakeReader:
    def __init__(self, page: dict, results: list[dict]) -> None:
        self.page = page
        self.results = results
        self.updated_at = "2026-08-14T00:00:00Z"
        self.batches: list[list[dict]] = []
        self.calls: list[dict | None] = []

    def search(self, _index_uid: str, queries: list[dict]) -> SearchSnapshot:
        self.batches.append(queries)
        self.calls.append(None)
        return SearchSnapshot({"results": [self.page, *self.results]}, self.updated_at)


class UpdatingReader(FakeReader):
    def search(self, index_uid: str, queries: list[dict]) -> SearchSnapshot:
        self.updated_at = "2026-08-14T00:00:01Z"
        return super().search(index_uid, queries)


class OverlapReader(FakeReader):
    def __init__(self, state: dict) -> None:
        super().__init__(_result(), [])
        self.state = state

    def search(self, index_uid: str, queries: list[dict]) -> SearchSnapshot:
        with self.state["lock"]:
            self.state["active"] += 1
            self.state["maximum"] = max(self.state["maximum"], self.state["active"])
            if self.state["active"] == 2:
                self.state["release"].set()
        self.state["release"].wait(0.2)
        result = super().search(index_uid, queries)
        with self.state["lock"]:
            self.state["active"] -= 1
        return result


def _result(hits=None, total=0, facets=None) -> dict:
    return {
        "hits": hits or [],
        "estimatedTotalHits": total,
        "facetDistribution": facets or {},
    }


def _full_hit() -> dict:
    return {
        "catalogId": "material:m-1",
        "id": "m-1",
        "kind": "material",
        "docClass": "material-full",
        "title": "科学家精神",
        "summary": "素材摘要",
        "accessLevel": "campus",
        "authority": "original",
        "materialType": "文档",
        "tags": ["思政"],
        "hasFile": True,
        "createdBy": "u-1",
    }


def _full_results() -> list[dict]:
    return [
        _result(facets={"kind": {"material": 1}}),
        _result(),
        _result(facets={"authority": {"original": 1}}),
        _result(facets={"materialType": {"文档": 1}}),
        _result(facets={"tags": {"思政": 1}}),
        _result(total=1),
        _result(total=1),
        _result(total=1),
        _result(facets={"accessLevel": {"campus": 1}}),
        _result(),
    ]


def _full_request() -> CatalogRequest:
    return CatalogRequest(
        q="科学家",
        kind="material",
        generation="test-generation",
        index_uid="catalog-generation-test",
        index_epoch="2026-08-14T00:00:00Z",
        page_size=20,
        offset=0,
        filters={"authority": ("original",), "materialType": ("文档",)},
        principal=Principal("u-1", "user"),
    )


def _page_request() -> CatalogRequest:
    return CatalogRequest(
        q="思政",
        kind="all",
        generation="test-generation",
        index_uid="catalog-generation-test",
        index_epoch="2026-08-14T00:00:00Z",
        page_size=20,
        offset=20,
        filters={},
        principal=Principal("u-1", "user"),
        include_metadata=False,
    )


def test_concurrent_searches_reach_the_catalog_together() -> None:
    state = {"active": 0, "maximum": 0, "lock": Lock(), "release": Event()}
    catalog = MeilisearchCatalog(OverlapReader(state))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(catalog.search, _page_request()) for _slot in range(2)]
        for future in futures:
            future.result()
    assert state["maximum"] == 2


def _assert_full_page(page) -> None:
    expected = [
        {
            "id": "m-1",
            "kind": "material",
            "title": "科学家精神",
            "summary": "素材摘要",
            "accessLevel": "campus",
            "authority": "original",
            "materialType": "文档",
            "tags": ["思政"],
            "hasFile": True,
            "contentAvailable": True,
            "score": 12,
        }
    ]
    assert page.items == expected
    metadata = page.metadata
    assert metadata is not None
    assert metadata.counts == {"all": 1, "case": 0, "knowledge": 0, "material": 1}
    assert (metadata.total, page.has_next, page.has_previous) == (1, False, False)
    assert metadata.facets["authority"] == [{"value": "original", "count": 1}]


def _restricted_hit() -> dict:
    return {
        "catalogId": "material:campus",
        "id": "campus",
        "kind": "material",
        "docClass": "material-restricted",
        "title": "校内蓝鲸",
        "summary": "绝密摘要",
        "sourceUrl": "https://secret.invalid",
        "tags": ["秘密"],
        "accessLevel": "campus",
        "hasFile": True,
    }


def _restricted_results() -> list[dict]:
    return [
        _result(facets={"kind": {"material": 1}}),
        _result(total=1),
        _result(),
        _result(),
        _result(),
        _result(),
        _result(),
        _result(),
        _result(),
        _result(),
    ]


def _restricted_request() -> CatalogRequest:
    return CatalogRequest(
        q="蓝鲸",
        kind="material",
        generation="test-generation",
        index_uid="catalog-generation-test",
        index_epoch="2026-08-14T00:00:00Z",
        page_size=1,
        offset=1,
        filters={},
        principal=Principal(None, "anonymous"),
    )


def _assert_restricted_page(page) -> None:
    assert page.items == [
        {
            "id": "campus",
            "kind": "material",
            "title": "校内蓝鲸",
            "accessLevel": "campus",
            "contentAvailable": False,
            "hasFile": True,
            "score": 12,
        }
    ]
    assert (page.metadata.total, page.has_next, page.has_previous) == (2, False, True)


def test_search_compiles_filters_and_normalizes_the_requested_page() -> None:
    client = FakeReader(_result([_full_hit()], 1), _full_results())
    page = MeilisearchCatalog(client).search(_full_request())
    _assert_full_page(page)
    assert len(client.batches) == 1
    query = client.batches[0][0]
    assert query["matchingStrategy"] == "frequency"
    assert 'docClass = "material-full"' in query["filter"]
    assert 'authority IN ["original"]' in query["filter"]


def test_restricted_title_hits_are_disjoint_redacted_and_unified() -> None:
    client = FakeReader(_result([_restricted_hit()], 2), _restricted_results())
    page = MeilisearchCatalog(client).search(_restricted_request())
    _assert_restricted_page(page)
    page_filter = client.batches[0][0]["filter"]
    assert (
        'kind = "material" AND docClass = "material-full" AND accessLevel = "public"'
    ) in page_filter
    assert (
        'kind = "material" AND accessLevel IN ["campus", "private"] '
        'AND docClass = "material-restricted" AND publicReferenceCount > 0'
    ) in page_filter
    assert client.calls == [None]
    assert client.batches[0][0]["offset"] == 1
    assert client.batches[0][0]["limit"] == 2


class HealthyReader:
    def __init__(
        self,
        status="available",
        primary_key="catalogId",
        generation="current-generation",
        epoch="epoch",
    ) -> None:
        self.status, self.primary_key = status, primary_key
        self.generation, self.epoch = generation, epoch

    def health(self, uid: str) -> CatalogHealth:
        assert uid == "catalog"
        return CatalogHealth(
            self.status == "available",
            self.primary_key,
            self.generation,
            self.epoch,
        )


def test_health_requires_available_server_and_stable_catalog_primary_key() -> None:
    MeilisearchCatalog(HealthyReader()).health("catalog", "current-generation", "epoch")
    for reader in (HealthyReader("unavailable"), HealthyReader(primary_key="id")):
        with pytest.raises(SearchUnavailable, match="检索暂不可用"):
            MeilisearchCatalog(reader).health("catalog", "current-generation", "epoch")


def test_health_requires_the_expected_catalog_generation() -> None:
    with pytest.raises(SearchUnavailable, match="检索暂不可用"):
        MeilisearchCatalog(HealthyReader(generation="stale")).health(
            "catalog",
            "current-generation",
            "epoch",
        )


def test_health_rejects_an_unconfirmed_index_epoch() -> None:
    with pytest.raises(SearchUnavailable, match="检索暂不可用"):
        MeilisearchCatalog(HealthyReader(epoch="late-write")).health(
            "catalog",
            "current-generation",
            "confirmed",
        )


def test_revocation_excludes_only_the_matching_catalog_kind() -> None:
    client = FakeReader(_result(), [])
    request = CatalogRequest(
        q="",
        kind="all",
        generation="test-generation",
        index_uid="catalog-generation-test",
        index_epoch="2026-08-14T00:00:00Z",
        page_size=20,
        offset=0,
        filters={},
        principal=Principal(None, "anonymous"),
        include_metadata=False,
        excluded_keys=(CatalogKey("case", "shared-id"),),
    )

    MeilisearchCatalog(client).search(request)

    page_filter = client.batches[0][0]["filter"]
    assert (
        'kind = "case" AND docClass = "case-public" AND id NOT IN ["shared-id"]'
        in page_filter
    )
    assert 'kind = "material" AND docClass = "material-full"' in page_filter
    restricted = page_filter.split('docClass = "material-restricted"')[1]
    assert 'id NOT IN ["shared-id"]' not in restricted


def test_search_rejects_an_index_update_during_the_query() -> None:
    client = UpdatingReader(_result([_full_hit()], 1), _full_results())

    with pytest.raises(SearchUnavailable, match="检索目录正在同步"):
        MeilisearchCatalog(client).search(_full_request())

    assert len(client.batches) == 1


def test_search_rejects_a_stable_but_unconfirmed_index_epoch() -> None:
    client = FakeReader(_result([_full_hit()], 1), _full_results())
    client.updated_at = "late-write"

    with pytest.raises(SearchUnavailable, match="检索目录正在同步"):
        MeilisearchCatalog(client).search(_full_request())

    assert len(client.batches) == 1


@pytest.mark.parametrize(
    ("principal", "expected"),
    [
        (Principal(None, "anonymous"), 'docClass = "case-public"'),
        (Principal("u-1", "user"), 'docClass = "case-private"'),
        (Principal("u-admin", "admin"), 'docClass = "case-private"'),
    ],
)
def test_case_query_uses_one_acl_document_per_case(principal, expected) -> None:
    client = FakeReader(_result(), [])
    request = CatalogRequest(
        q="附件",
        kind="case",
        generation="test-generation",
        index_uid="catalog-generation-test",
        index_epoch="2026-08-14T00:00:00Z",
        page_size=20,
        offset=0,
        filters={},
        principal=principal,
        include_metadata=False,
    )

    MeilisearchCatalog(client).search(request)

    case_filter = client.batches[0][0]["filter"]
    assert expected in case_filter
    assert ("createdBy" in case_filter) is (principal.role == "user")
