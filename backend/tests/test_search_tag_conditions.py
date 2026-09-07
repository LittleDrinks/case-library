"""标签条件（flat/嵌套）请求、编译与计数的契约测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.modules.search.meilisearch import (
    CatalogMetadata,
    CatalogPage,
    CatalogRequest,
    Principal,
    _facet_payload,
    _full_scope,
    _restricted_business,
)
from app.modules.search.models import SearchQuery, SearchRequest, TagExpression, TagLeaf

TAG_A = "tag-seed-4-1"
TAG_B = "tag-seed-4-2"
TAG_C = "tag-seed-1-4"
EPOCH = "2026-08-14T00:00:00Z"


class RecordingCatalog:
    def __init__(self) -> None:
        self.requests: list[CatalogRequest] = []

    def health(self, *_args) -> None:
        return None

    def search(self, request) -> CatalogPage:
        self.requests.append(request)
        metadata = None
        if request.include_metadata:
            metadata = CatalogMetadata(
                0, {"all": 0, "case": 0, "knowledge": 0, "material": 0}, {}
            )
        return CatalogPage([], metadata, True, request.offset > 0)


def _login(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "user", "password": "user123"})


def _use(client: TestClient) -> RecordingCatalog:
    catalog = RecordingCatalog()
    client.app.state.search_catalog = catalog
    return catalog


def test_flat_tag_mode_builds_normalized_condition() -> None:
    query = SearchQuery(tagMode="any", tagIds=[TAG_A, TAG_B, TAG_A])
    condition = query.condition()
    assert condition.op == "or"
    assert [leaf.tagId for leaf in condition.children] == [TAG_A, TAG_B]
    assert SearchQuery(tagIds=[TAG_A]).condition().op == "and"
    assert SearchQuery().condition() is None


def test_nested_expression_rejects_conflicting_flat_condition() -> None:
    nested = {
        "op": "and",
        "children": [
            {"op": "or", "children": [{"tagId": TAG_A}, {"tagId": TAG_B}]},
            {"tagId": TAG_C},
        ],
    }
    request = SearchRequest(tagExpression=nested)
    assert request.condition().op == "and"
    with pytest.raises(ValidationError):
        SearchRequest(tagExpression=nested, tagIds=[TAG_A])
    with pytest.raises(ValidationError):
        SearchRequest(tagExpression=nested, tagMode="any")
    with pytest.raises(ValidationError):
        TagExpression(op="xor", children=[{"tagId": TAG_A}])
    with pytest.raises(ValidationError):
        TagExpression(op="and", children=[])


def test_get_search_applies_flat_tag_condition(client: TestClient) -> None:
    catalog = _use(client)
    _login(client)
    response = client.get(
        "/api/search",
        params={"kind": "case", "tagMode": "any", "tagIds": [TAG_A, TAG_B]},
    )
    assert response.status_code == 200
    request = catalog.requests[0]
    assert request.tag_condition.op == "or"
    assert request.tag_condition.children[1].tagId == TAG_B
    assert response.json()["tagCondition"]["op"] == "or"


def test_post_search_accepts_nested_mixed_condition(client: TestClient) -> None:
    catalog = _use(client)
    _login(client)
    body = {
        "kind": "case",
        "tagExpression": {
            "op": "and",
            "children": [
                {"op": "or", "children": [{"tagId": TAG_A}, {"tagId": TAG_B}]},
                {"tagId": TAG_C},
            ],
        },
    }
    assert client.post("/api/search", json=body).status_code == 200
    condition = catalog.requests[0].tag_condition
    assert condition.op == "and"
    assert condition.children[0].op == "or"


def test_post_search_rejects_conflicting_conditions(client: TestClient) -> None:
    _use(client)
    _login(client)
    nested = {"op": "or", "children": [{"tagId": TAG_A}]}
    conflict = client.post(
        "/api/search", json={"tagExpression": nested, "tagIds": [TAG_A]}
    )
    assert conflict.status_code == 422
    mode_conflict = client.post(
        "/api/search", json={"tagExpression": nested, "tagMode": "any"}
    )
    assert mode_conflict.status_code == 422


def test_unknown_tag_ids_fail_with_422(client: TestClient) -> None:
    catalog = _use(client)
    _login(client)
    missing = client.get("/api/search", params={"tagIds": [TAG_A, "tag-missing"]})
    assert missing.status_code == 422
    assert "tag-missing" in missing.json()["detail"]
    nested = client.post(
        "/api/search",
        json={"tagExpression": {"op": "or", "children": [{"tagId": "tag-none"}]}},
    )
    assert nested.status_code == 422
    assert catalog.requests == []


def test_tag_condition_changes_invalidate_pagination_cursor(client: TestClient) -> None:
    _use(client)
    _login(client)
    first = client.get("/api/search", params={"q": "蓝鲸", "tagIds": [TAG_A]}).json()
    assert first["nextCursor"]
    changed = client.get(
        "/api/search",
        params={
            "q": "蓝鲸",
            "tagIds": [TAG_A],
            "cursor": first["nextCursor"],
        },
    )
    assert changed.status_code == 200
    different = client.get(
        "/api/search",
        params={"q": "蓝鲸", "cursor": first["nextCursor"]},
    )
    assert different.status_code == 422


def _request(**changes) -> CatalogRequest:
    values = {
        "q": "",
        "kind": "case",
        "generation": "test-generation",
        "index_uid": "catalog-generation-test",
        "index_epoch": EPOCH,
        "page_size": 20,
        "offset": 0,
        "filters": {},
        "principal": Principal(None, "anonymous"),
    }
    return CatalogRequest(**{**values, **changes})


def _nested() -> TagExpression:
    return TagExpression(
        op="and",
        children=[
            TagExpression(op="or", children=[TagLeaf(tagId=TAG_A), TagLeaf(tagId=TAG_B)]),
            TagLeaf(tagId=TAG_C),
        ],
    )


def test_nested_condition_compiles_to_parenthesized_filter() -> None:
    expected = ' '.join(
        [
            'kind = "case"',
            'AND docClass = "case-public"',
            'AND ((tagIds = "tag-seed-4-1" OR tagIds = "tag-seed-4-2")',
            'AND tagIds = "tag-seed-1-4")',
        ]
    )
    assert _full_scope(_request(tag_condition=_nested())) == expected


def test_tag_condition_prunes_non_case_branches() -> None:
    from app.modules.search.meilisearch import NEVER

    request = _request(kind="all", tag_condition=TagLeaf(tagId=TAG_A))
    filter_value = _full_scope(request)
    assert 'kind = "material"' not in filter_value
    assert 'kind = "knowledge"' not in filter_value
    assert "tagIds" in filter_value
    assert _restricted_business(request) == NEVER


def test_catalog_facet_counts_within_full_current_condition() -> None:
    condition = TagExpression(
        op="or", children=[TagLeaf(tagId=TAG_A), TagLeaf(tagId=TAG_B)]
    )
    request = _request(
        filters={"typeName": ("人物传记类",)},
        tag_condition=condition,
    )
    catalog = _facet_payload(request, "tagCatalog", "idx")
    assert catalog["facets"] == ["tagIds"]
    assert "tagIds" in catalog["filter"]
    assert 'typeName IN ["人物传记类"]' in catalog["filter"]
    assert '(tagIds = "tag-seed-4-1" OR tagIds = "tag-seed-4-2")' in catalog["filter"]

    typed = _facet_payload(request, "typeName", "idx")
    assert "typeName" not in typed["filter"]
    assert "tagIds" in typed["filter"]


def test_free_tag_facet_stays_material_only() -> None:
    from app.modules.search.meilisearch import FACETS, NEVER

    assert "tagCatalog" in FACETS["case"]
    assert "tag" not in FACETS["case"]
    assert "tag" in FACETS["material"]
    request = _request(filters={"tag": ("科学家精神",)})
    assert _full_scope(request) == NEVER
