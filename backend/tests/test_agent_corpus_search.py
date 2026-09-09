"""#232 Agent search_corpus：结构化条件、目录发现、有界分页与权限。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import Tool

from app.modules.agent.deps import ToolDeps
from app.modules.agent.search import CorpusSearchParams, search_corpus
from app.modules.agent.source_reader import read_source as read_domain_source
from app.modules.search.meilisearch import CatalogMetadata, CatalogPage
from tests.test_agent_grounding import _auth, _stream_post, _tool_model


class PagedCatalog:
    """预制条目的目录桩：按 offset 有界分页，记录请求供调用链断言。"""

    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.requests: list = []

    def health(self, *_args) -> None:
        return None

    def search(self, request):
        self.requests.append(request)
        page = self.items[request.offset:request.offset + request.page_size]
        has_next = request.offset + len(page) < len(self.items)
        return CatalogPage(page, self._metadata(request), has_next, request.offset > 0)

    def _metadata(self, request) -> CatalogMetadata | None:
        if not request.include_metadata:
            return None
        counts = {"all": len(self.items), "case": len(self.items),
                  "knowledge": 0, "material": 0}
        return CatalogMetadata(len(self.items), counts, {})


def _case_item(item_id: str) -> dict:
    return {"id": item_id, "kind": "case", "title": f"案例{item_id}", "score": 10}


def _restricted_item() -> dict:
    return {
        "id": "m-restricted", "kind": "material", "title": "校内受限素材",
        "accessLevel": "campus", "contentAvailable": False, "hasFile": False,
        "score": 1,
    }


def _deps(client: TestClient, catalog: PagedCatalog, user: dict | None = None) -> ToolDeps:
    client.app.state.search_catalog = catalog
    return ToolDeps(
        database=client.app.state.database,
        case_id="c-draft-1", thread_id="t-corpus", run_id="r-corpus",
        user=user or {"id": "u-user-demo", "role": "user"},
        catalog=catalog, catalog_state=client.app.state.catalog_state,
        secret_path=client.app.state.settings.app_secret_file,
    )


def _call(deps: ToolDeps, arguments: dict) -> dict:
    params = CorpusSearchParams.model_validate(arguments)
    return asyncio.run(search_corpus(SimpleNamespace(deps=deps), params))


def test_tool_schema_is_bounded_and_rejects_unknown_fields() -> None:
    schema = Tool(search_corpus, takes_ctx=True).tool_def.parameters_json_schema

    assert schema["additionalProperties"] is False
    assert schema["properties"]["pageSize"]["maximum"] == 20
    assert schema["properties"]["tagIds"]["description"]
    assert "TagExpression" in schema.get("$defs", {})


def test_params_reject_unknown_fields_instead_of_dropping() -> None:
    with pytest.raises(ValidationError) as excinfo:
        CorpusSearchParams.model_validate({"query": "x", "webSearch": True})
    assert "webSearch" in str(excinfo.value)


def test_structured_arguments_reach_catalog_request(client) -> None:
    catalog = PagedCatalog([_case_item("c-1")])
    view = _call(_deps(client, catalog), {
        "query": "科学家精神", "kind": "case",
        "tagIds": ["tag-seed-4-1"], "tagMode": "any",
    })

    request = catalog.requests[0]
    assert request.q == "科学家精神" and request.kind == "case"
    assert request.tag_condition.op == "or"
    assert request.page_size == 5 and request.principal.user_id == "u-user-demo"
    assert view["total"] == 1
    assert {"id": "tag-seed-4-1", "name": "科学家精神",
            "group": "思政元素"} in view["tagCatalog"]


def test_empty_arguments_discover_catalog_and_scale(client) -> None:
    view = _call(_deps(client, PagedCatalog([])), {})

    assert view["page"] == 1 and view["total"] == 0
    assert any(row["name"] == "科学家精神" for row in view["tagCatalog"])
    assert view["nextCursor"] is None


def test_pagination_serves_disjoint_pages_with_cursor(client) -> None:
    catalog = PagedCatalog([_case_item(f"c-{index}") for index in range(8)])
    deps = _deps(client, catalog)
    first = _call(deps, {"query": "案例"})
    second = _call(deps, {"query": "案例", "cursor": first["nextCursor"]})

    assert [source["id"] for source in first["sources"]] == [f"c-{i}" for i in range(5)]
    assert [source["id"] for source in second["sources"]] == [f"c-{i}" for i in range(5, 8)]
    assert catalog.requests[1].offset == 5 and second["previousCursor"]


def test_cursor_rejected_after_conditions_change(client) -> None:
    items = [_case_item(f"c-{index}") for index in range(8)]
    deps = _deps(client, PagedCatalog(items))
    first = _call(deps, {"query": "案例", "tagIds": ["tag-seed-4-1"]})

    with pytest.raises(ModelRetry) as excinfo:
        _call(deps, {
            "query": "案例", "tagIds": ["tag-seed-4-2"],
            "cursor": first["nextCursor"],
        })
    assert "游标无效" in str(excinfo.value)


def test_malformed_cursor_is_rejected(client) -> None:
    items = [_case_item(f"c-{index}") for index in range(8)]
    deps = _deps(client, PagedCatalog(items))

    with pytest.raises(ModelRetry) as excinfo:
        _call(deps, {"query": "案例", "cursor": "tampered.signature"})
    assert "游标无效" in str(excinfo.value)


def test_unknown_tag_id_fails_explicitly(client) -> None:
    deps = _deps(client, PagedCatalog([]))

    with pytest.raises(ModelRetry) as excinfo:
        _call(deps, {"tagIds": ["tag-missing"]})
    assert "标签不存在" in str(excinfo.value)


def test_expression_plus_tag_ids_fails_explicitly(client) -> None:
    deps = _deps(client, PagedCatalog([]))

    with pytest.raises(ModelRetry) as excinfo:
        _call(deps, {
            "tagIds": ["tag-seed-4-1"],
            "tagExpression": {"op": "or", "children": [{"tagId": "tag-seed-4-1"}]},
        })
    assert "同时使用" in str(excinfo.value)


def test_restricted_hit_records_reference_without_content_leak(client) -> None:
    database = client.app.state.database
    database.materials.insert_one({
        "id": "m-restricted", "status": "active", "title": "校内受限素材",
        "accessLevel": "campus", "createdBy": "u-other",
    })
    deps = _deps(client, PagedCatalog([_restricted_item()]))
    view = _call(deps, {"kind": "material"})

    source = view["sources"][0]
    assert source["title"] == source["snippet"] == "校内受限素材"
    assert "content" not in source and "summary" not in source
    result = read_domain_source(
        deps.database, None, deps.user, deps.case_id, "material", "m-restricted",
    )
    assert result["status"] == "no_access"


def _discovery_model(outputs: list) -> FunctionModel:
    return _tool_model(
        "search_corpus", {}, "corpus-discover-search", outputs, "已列出平台标签目录。",
    )


def test_empty_query_through_stream_discovers_real_catalog(client) -> None:
    auth = _auth(client)
    outputs: list[dict] = []
    response = _stream_post(
        client, auth, "c-draft-1", "corpus-discover-message",
        "corpus-discover-user-message",
        [{"type": "text", "text": "看看平台里有哪些标签"}], _discovery_model(outputs),
    )

    assert response.status_code == 200, response.text
    assert outputs[0]["scope"] == "platform"
    assert any(row["id"] == "tag-seed-4-1" for row in outputs[0]["tagCatalog"])
