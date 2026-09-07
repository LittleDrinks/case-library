"""#164 REVISE：/api/search 响应模型契约（OpenAPI 严格 schema 与字段完整性）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

TAG_A = "tag-seed-4-1"
TAG_B = "tag-seed-4-2"

RESPONSE_KEYS = {
    "query",
    "kind",
    "tagCondition",
    "page",
    "pageSize",
    "items",
    "total",
    "counts",
    "facets",
    "metadataIncluded",
    "nextCursor",
    "previousCursor",
}


class RecordingCatalog:
    def __init__(self, items: list[dict]) -> None:
        from app.modules.search.meilisearch import CatalogMetadata, CatalogPage

        self.items = items
        self.requests: list[object] = []
        self._metadata_type = CatalogMetadata
        self._page_type = CatalogPage

    def health(self, *_args) -> None:
        return None

    def search(self, request):
        self.requests.append(request)
        end = request.offset + request.page_size
        page = self._page_type(
            self.items[request.offset : end],
            self._metadata(request),
            end < len(self.items),
            request.offset > 0,
        )
        return page

    def _metadata(self, request):
        if not request.include_metadata:
            return None
        counts = {"all": 3, "case": 1, "knowledge": 0, "material": 2}
        facets = {
            "tagCatalog": [{"value": TAG_A, "count": 1}, {"value": TAG_B, "count": 1}],
        }
        return self._metadata_type(len(self.items), counts, facets)


def _catalog_items() -> list[dict]:
    return [_case_item(), _material_item(), _restricted_item()]


def _case_item() -> dict:
    return {
        "id": "c-1",
        "kind": "case",
        "title": "案例一",
        "summary": "摘要",
        "typeName": "人物传记类",
        "tagIds": [TAG_A],
        "score": 9,
    }


def _material_item() -> dict:
    return {
        "id": "m-1",
        "kind": "material",
        "title": "素材一",
        "accessLevel": "public",
        "contentAvailable": True,
        "hasFile": True,
        "score": 4,
    }


def _restricted_item() -> dict:
    return {
        "id": "m-r",
        "kind": "material",
        "title": "受限素材",
        "accessLevel": "campus",
        "contentAvailable": False,
        "hasFile": True,
        "score": 2,
    }


def _use(client: TestClient) -> RecordingCatalog:
    catalog = RecordingCatalog(_catalog_items())
    client.app.state.search_catalog = catalog
    return catalog


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"username": "user", "password": "user123"}
    )
    assert response.status_code == 200


def test_openapi_declares_strict_search_response_for_both_verbs(client) -> None:
    schema = client.app.openapi()
    operation = schema["paths"]["/api/search"]
    for verb in ("get", "post"):
        ref = operation[verb]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert ref == {"$ref": "#/components/schemas/SearchResponse"}
    response_schema = schema["components"]["schemas"]["SearchResponse"]
    assert set(response_schema["properties"]) == RESPONSE_KEYS
    item_schema = schema["components"]["schemas"]["SearchItem"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["required"]) == {"id", "kind", "title", "score"}
    counts = schema["components"]["schemas"]["CountSummary"]["properties"]
    assert set(counts) == {"all", "case", "knowledge", "material"}


def _get_tagged_page(client: TestClient) -> dict:
    response = client.get("/api/search", params={"q": "蓝鲸", "tagIds": [TAG_A]})
    assert response.status_code == 200
    return response.json()


def _assert_summary(payload: dict) -> None:
    assert payload["total"] == 3 and payload["metadataIncluded"] is True
    assert payload["counts"] == {
        "all": 3,
        "case": 1,
        "knowledge": 0,
        "material": 2,
    }
    assert payload["facets"]["tagCatalog"] == [
        {"value": TAG_A, "count": 1},
        {"value": TAG_B, "count": 1},
    ]


def test_get_response_carries_the_full_contract(client: TestClient) -> None:
    _use(client)
    _login(client)
    payload = _get_tagged_page(client)
    assert set(payload) == RESPONSE_KEYS
    _assert_summary(payload)
    assert payload["tagCondition"] == {
        "op": "and",
        "children": [{"tagId": TAG_A}],
    }
    case_item = payload["items"][0]
    assert case_item["kind"] == "case" and case_item["tagIds"] == [TAG_A]
    assert {"id", "kind", "title", "score"} <= set(case_item)
    assert payload["items"][1]["contentAvailable"] is True


def test_restricted_items_keep_field_absence_contract(client: TestClient) -> None:
    _use(client)
    _login(client)
    payload = _get_tagged_page(client)
    assert payload["items"][2] == {
        "id": "m-r",
        "kind": "material",
        "title": "受限素材",
        "accessLevel": "campus",
        "contentAvailable": False,
        "hasFile": True,
        "score": 2,
    }
    assert "summary" not in payload["items"][1]


def test_case_items_resolve_tag_names_from_catalog(client: TestClient) -> None:
    _use(client)
    _login(client)
    payload = _get_tagged_page(client)
    assert payload["items"][0]["tagNames"] == ["科学家精神"]
    assert "tagNames" not in payload["items"][1]
    assert "tagNames" not in payload["items"][2]


def test_post_response_echoes_nested_tag_condition(client: TestClient) -> None:
    _use(client)
    _login(client)
    body = {
        "kind": "case",
        "tagExpression": {
            "op": "or",
            "children": [{"tagId": TAG_A}, {"tagId": TAG_B}],
        },
    }
    payload = client.post("/api/search", json=body).json()
    assert set(payload) == RESPONSE_KEYS
    assert payload["tagCondition"]["op"] == "or"
    assert payload["tagCondition"]["children"][1]["tagId"] == TAG_B
    assert payload["items"][0]["typeName"] == "人物传记类"


def test_following_page_omits_metadata_but_keeps_contract(client: TestClient) -> None:
    _use(client)
    _login(client)
    first = client.get("/api/search", params={"q": "蓝鲸", "pageSize": 1}).json()
    assert first["nextCursor"]
    payload = client.get(
        "/api/search",
        params={"q": "蓝鲸", "pageSize": 1, "cursor": first["nextCursor"]},
    ).json()
    assert set(payload) == RESPONSE_KEYS
    assert payload["page"] == 2
    assert payload["metadataIncluded"] is False
    assert payload["total"] is None
    assert payload["counts"] is None
    assert payload["facets"] is None
