from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.modules.search.meilisearch import (
    CatalogKey,
    CatalogMetadata,
    CatalogPage,
    SearchUnavailable,
)
from app.modules.search.outbox import SearchOutbox


class RecordingCatalog:
    def __init__(self, error: Exception | None = None, callback=None) -> None:
        self.requests = []
        self.error = error
        self.callback = callback

    def health(
        self, _index_uid: str, _expected_generation: str, _expected_epoch: str
    ) -> None:
        return None

    def search(self, request) -> CatalogPage:
        self.requests.append(request)
        if self.callback:
            self.callback()
        if self.error:
            raise self.error
        return CatalogPage(
            [_case_item()], _metadata(request), False, request.offset > 0
        )


def _case_item() -> dict:
    return {"id": "c-02", "kind": "case", "title": "公开案例", "score": 12}


def _metadata(request) -> CatalogMetadata | None:
    if not request.include_metadata:
        return None
    return CatalogMetadata(
        1,
        {"all": 1, "case": 1, "knowledge": 0, "material": 0},
        {"typeName": [{"value": "校本实践类", "count": 1}]},
    )


def _use(client: TestClient, catalog: RecordingCatalog) -> RecordingCatalog:
    client.app.state.search_catalog = catalog
    return catalog


def _login(client: TestClient, username: str = "user") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": f"{username}123"},
    )
    assert response.status_code == 200


def test_search_route_preserves_envelope_and_compiles_user_scope(client: TestClient) -> None:
    catalog = _use(client, RecordingCatalog())
    _login(client)
    response = client.get("/api/search", params={"q": "科学家精神", "kind": "case", "typeName": "校本实践类"})
    assert response.status_code == 200
    assert response.json()["counts"]["case"] == 1
    request = catalog.requests[0]
    assert request.principal.user_id == "u-user-demo"
    assert request.generation == "test-generation"
    assert request.index_uid == "catalog-generation-test"
    assert request.index_epoch == "test-epoch"
    assert request.filters == {"typeName": ("校本实践类",)}


def _public_case(client: TestClient) -> str:
    database = client.app.state.database
    database.cases.insert_one(
        {
            "id": "c-mounted-public",
            "ownerId": "u-admin-demo",
            "publicationStatus": "public",
            "publishedVersionId": "v-mounted-public",
        }
    )
    return "c-mounted-public"


def _replace_generation(database) -> None:
    database.search_catalog_generation.update_one({"_id": "catalog"}, {"$set": {"generation": "next-generation", "indexUid": "catalog-generation-next"}})


def test_mounted_public_case_uses_published_version_for_non_owner(
    client: TestClient,
) -> None:
    catalog = _use(client, RecordingCatalog())
    _login(client)
    response = client.get(
        "/api/search",
        params={
            "kind": "material",
            "mountedInCaseId": _public_case(client),
        },
    )
    assert response.status_code == 200
    mounted = catalog.requests[0].mounted_filter
    assert (mounted.field, mounted.value) == ("publishedVersionIds", "v-mounted-public")


def test_revocations_are_passed_to_catalog_and_backlog_fails_closed(client: TestClient) -> None:
    catalog, collection = _use(client, RecordingCatalog()), client.app.state.database.search_revocations
    collection.insert_one({"_id": "case:c-02", "logicalKey": "case:c-02", "id": "c-02"})
    assert client.get("/api/search").status_code == 200
    assert catalog.requests[0].excluded_keys == (CatalogKey("case", "c-02"),)
    collection.insert_many(
        {
            "_id": f"material:m-{index}",
            "logicalKey": f"material:m-{index}",
            "id": f"m-{index}",
        }
        for index in range(101)
    )
    response = client.get("/api/search")
    assert (response.status_code, response.json()["detail"]) == (503, "检索目录正在同步")


def test_search_unavailability_is_a_public_503(client: TestClient) -> None:
    _use(client, RecordingCatalog(SearchUnavailable("检索暂不可用")))
    response = client.get("/api/search")
    assert (response.status_code, response.json()["detail"]) == (503, "检索暂不可用")


def test_search_rejects_a_missing_catalog_generation(client: TestClient) -> None:
    client.app.state.database.search_catalog_generation.delete_many({})

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (
        503,
        "检索目录正在同步",
    )


def test_search_rejects_an_active_catalog_rebuild(client: TestClient) -> None:
    SearchOutbox(client.app.state.database).pause("active-rebuild")

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (
        503,
        "检索目录正在同步",
    )


def test_search_rejects_a_hot_key_pending_beyond_the_lag_budget(
    client: TestClient,
) -> None:
    client.app.state.database.search_outbox.insert_one(
        {
            "_id": "case:c-1",
            "sequence": 1,
            "appliedSequence": -1,
            "pendingSince": datetime.now(UTC) - timedelta(seconds=11),
            "updatedAt": datetime.now(UTC),
        }
    )

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (
        503,
        "检索目录正在同步",
    )


def test_search_rejects_a_missing_worker_heartbeat(client: TestClient) -> None:
    client.app.state.database.search_worker_state.delete_many({})

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (
        503,
        "检索目录正在同步",
    )


def test_search_rejects_a_stale_worker_heartbeat(client: TestClient) -> None:
    client.app.state.database.search_worker_state.update_one(
        {"_id": "catalog"},
        {"$set": {"updatedAt": datetime.now(UTC) - timedelta(seconds=11)}},
    )

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (
        503,
        "检索目录正在同步",
    )


def _revoke_case(database) -> None:
    sequence = database.search_control.find_one_and_update(
        {"_id": "catalog"},
        {"$inc": {"sequence": 1}},
        upsert=True,
        return_document=True,
    )["sequence"]
    database.search_revocations.update_one(
        {"_id": "case:c-02"},
        {
            "$set": {
                "logicalKey": "case:c-02",
                "id": "c-02",
                "sequence": sequence,
            }
        },
        upsert=True,
    )


def test_search_retries_when_a_revocation_commits_during_query(
    client: TestClient,
) -> None:
    database = client.app.state.database
    calls = 0

    def revoke_once() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            _revoke_case(database)

    catalog = _use(client, RecordingCatalog(callback=revoke_once))
    response = client.get("/api/search")

    assert response.status_code == 200
    assert len(catalog.requests) == 2
    assert catalog.requests[1].excluded_keys == (CatalogKey("case", "c-02"),)


def test_search_fails_closed_when_catalog_sequence_never_stabilizes(
    client: TestClient,
) -> None:
    database = client.app.state.database
    catalog = _use(client, RecordingCatalog(callback=lambda: _revoke_case(database)))

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (
        503,
        "检索目录正在同步",
    )
    assert len(catalog.requests) == 3


def test_search_fails_closed_when_generation_changes_during_query(
    client: TestClient,
) -> None:
    database = client.app.state.database

    _use(client, RecordingCatalog(callback=lambda: _replace_generation(database)))

    response = client.get("/api/search")

    assert (response.status_code, response.json()["detail"]) == (503, "检索目录正在同步")
