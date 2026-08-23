from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.modules.search.meilisearch import CatalogMetadata, CatalogPage


def _items(count: int) -> list[dict]:
    return [
        {
            "id": f"m-{index:02}",
            "kind": "material",
            "title": f"素材 {index:02}",
            "score": 1,
        }
        for index in range(count)
    ]


class SequenceCatalog:
    def __init__(self, count: int = 23) -> None:
        self.items = _items(count)
        self.requests = []

    def health(
        self, _index_uid: str, _expected_generation: str, _expected_epoch: str
    ) -> None:
        return None

    def search(self, request) -> CatalogPage:
        self.requests.append(request)
        end = request.offset + request.page_size
        metadata = self._metadata(request)
        return CatalogPage(
            self.items[request.offset : end],
            metadata,
            end < len(self.items),
            request.offset > 0,
        )

    def _metadata(self, request) -> CatalogMetadata | None:
        if not request.include_metadata:
            return None
        counts = {
            "all": len(self.items),
            "case": 0,
            "knowledge": 0,
            "material": len(self.items),
        }
        return CatalogMetadata(len(self.items), counts, {})


def _catalog(client: TestClient, count: int = 23) -> SequenceCatalog:
    catalog = SequenceCatalog(count)
    client.app.state.search_catalog = catalog
    return catalog


def _get(client: TestClient, **params) -> dict:
    response = client.get("/api/search", params=params)
    assert response.status_code == 200
    return response.json()


def _three_pages(client: TestClient) -> list[dict]:
    params, pages = {"q": "素材", "kind": "material", "pageSize": 10}, []
    for _index in range(3):
        page = _get(client, **params)
        pages.append(page)
        params["cursor"] = page["nextCursor"]
    return pages


def test_cursor_walks_forward_and_back_without_entering_the_url_contract(
    client: TestClient,
) -> None:
    _catalog(client)
    pages = _three_pages(client)
    ids = [row["id"] for page in pages for row in page["items"]]
    previous = _get(
        client,
        q="素材",
        kind="material",
        pageSize=10,
        cursor=pages[-1]["previousCursor"],
    )
    assert (len(ids), len(set(ids)), previous["page"]) == (23, 23, 2)
    assert previous["items"] == pages[1]["items"]
    assert pages[1]["metadataIncluded"] is False


def _first_cursor(client: TestClient, **params) -> str:
    _catalog(client, 11)
    return _get(client, q="素材", kind="material", pageSize=10, **params)["nextCursor"]


def test_cursor_is_bound_to_query_and_filters(client: TestClient) -> None:
    cursor = _first_cursor(client, authority="original")
    changed_query = client.get(
        "/api/search",
        params={
            "q": "另一个查询",
            "kind": "material",
            "pageSize": 10,
            "authority": "original",
            "cursor": cursor,
        },
    )
    changed_filter = client.get(
        "/api/search",
        params={
            "q": "素材",
            "kind": "material",
            "pageSize": 10,
            "authority": "secondary",
            "cursor": cursor,
        },
    )
    assert (changed_query.status_code, changed_filter.status_code) == (422, 422)


def test_cursor_normalizes_whitespace_in_query_scope(client: TestClient) -> None:
    cursor = _first_cursor(client)
    response = client.get(
        "/api/search",
        params={
            "q": "  素材  ",
            "kind": "material",
            "pageSize": 10,
            "cursor": cursor,
        },
    )
    assert response.status_code == 200
    assert response.json()["page"] == 2


def test_cursor_is_bound_to_the_catalog_generation(client: TestClient) -> None:
    cursor = _first_cursor(client)
    client.app.state.database.search_catalog_generation.update_one(
        {"_id": "catalog"},
        {"$set": {"generation": "next-generation"}},
    )

    response = client.get(
        "/api/search",
        params={
            "q": "素材",
            "kind": "material",
            "pageSize": 10,
            "cursor": cursor,
        },
    )

    assert response.status_code == 422


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200


def test_cursor_is_bound_to_the_authenticated_principal(client: TestClient) -> None:
    _catalog(client, 11)
    _login(client, "admin", "admin123")
    cursor = _get(client, q="素材", kind="material", pageSize=10)["nextCursor"]
    client.cookies.clear()
    _login(client, "user", "user123")
    response = client.get(
        "/api/search",
        params={
            "q": "素材",
            "kind": "material",
            "pageSize": 10,
            "cursor": cursor,
        },
    )
    assert response.status_code == 422


def test_cursor_survives_a_new_session_for_the_same_principal(
    client: TestClient,
) -> None:
    _catalog(client, 11)
    _login(client, "user", "user123")
    cursor = _get(client, q="素材", kind="material", pageSize=10)["nextCursor"]
    client.cookies.clear()
    _login(client, "user", "user123")
    assert (
        _get(
            client,
            q="素材",
            kind="material",
            pageSize=10,
            cursor=cursor,
        )["page"]
        == 2
    )


def test_tampered_and_unsigned_cursors_are_rejected(client: TestClient) -> None:
    cursor = _first_cursor(client)
    tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
    for value in (tampered, cursor.split(".")[0]):
        response = client.get(
            "/api/search",
            params={
                "q": "素材",
                "kind": "material",
                "pageSize": 10,
                "cursor": value,
            },
        )
        assert response.status_code == 422


def test_cursor_requires_the_application_secret(client: TestClient) -> None:
    client.app.state.settings = replace(client.app.state.settings, app_secret_file="")
    assert client.get("/api/search").status_code == 503


def test_numeric_and_oversized_cursor_inputs_are_rejected(client: TestClient) -> None:
    assert client.get("/api/search", params={"page": 2}).status_code == 422
    response = client.get("/api/search", params={"cursor": "x" * 2_001})
    assert response.status_code == 422
