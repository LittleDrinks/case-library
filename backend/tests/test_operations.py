from __future__ import annotations

from datetime import UTC, datetime, timedelta

import mongomock
import pytest
from fastapi.testclient import TestClient
from urllib3.exceptions import HTTPError

from app.core.config import Settings
from app.core.database import connect
from app.main import create_app
from app.modules.search.client import CatalogHealth
from app.modules.search.meilisearch import SearchUnavailable
from app.modules.search.outbox import SearchOutbox
from conftest import MemoryBlobStore, ReadyCatalogState


def test_health_and_constants_are_available(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert client.get("/api/constants").json() == {
        "caseWorkflowStatuses": ["draft", "pending", "reviewing", "published"],
        "casePublicationStatuses": ["none", "public", "hidden"],
        "roles": ["user", "admin"],
        "csrfHeader": "X-CSRF-Token",
    }


@pytest.mark.parametrize("error", [OSError("offline"), HTTPError("offline")])
def test_readiness_rejects_unavailable_object_store(
    client: TestClient,
    error: Exception,
) -> None:
    class UnavailableBlobStore:
        def health(self) -> None:
            raise error

    client.app.state.blob_store = UnavailableBlobStore()

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Object storage unavailable"}


def test_search_unavailable_is_a_service_failure(client: TestClient) -> None:
    class UnavailableSearchCatalog:
        def search(self, _request):
            raise SearchUnavailable("检索暂不可用")

    client.app.state.search_catalog = UnavailableSearchCatalog()

    response = client.get("/api/search?q=科学家精神")

    assert response.status_code == 503
    assert response.json() == {"detail": "检索暂不可用"}


def test_readiness_rejects_unavailable_search_catalog(client: TestClient) -> None:
    class UnavailableSearchCatalog:
        def health(
            self, _index_uid: str, _expected_generation: str, _expected_epoch: str
        ) -> None:
            raise SearchUnavailable("检索暂不可用")

    client.app.state.search_catalog = UnavailableSearchCatalog()

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Search catalog unavailable"}


def test_readiness_rejects_search_catalog_rebuild(client: TestClient) -> None:
    SearchOutbox(client.app.state.database).pause("active-rebuild")

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Search catalog unavailable"}


def test_readiness_ignores_an_expired_rebuild_lease(client: TestClient) -> None:
    expired = datetime.now(UTC) - timedelta(seconds=1)
    client.app.state.database.search_catalog_state.insert_one(
        {
            "_id": "catalog",
            "leaseOwner": "crashed-rebuild",
            "leaseExpiresAt": expired,
        }
    )

    assert client.get("/health/ready").json() == {"status": "ready"}


def test_readiness_rejects_missing_catalog_generation(client: TestClient) -> None:
    client.app.state.database.search_catalog_generation.delete_many({})

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Search catalog unavailable"}


def test_readiness_rejects_stale_search_outbox(client: TestClient) -> None:
    client.app.state.database.search_outbox.insert_one(
        {
            "_id": "case:c-1",
            "sequence": 1,
            "appliedSequence": -1,
            "pendingSince": datetime.now(UTC) - timedelta(seconds=11),
            "updatedAt": datetime.now(UTC),
        }
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Search catalog unavailable"}


def test_readiness_allows_search_outbox_propagation_window(client: TestClient) -> None:
    client.app.state.database.search_outbox.insert_one(
        {
            "_id": "case:c-1",
            "sequence": 1,
            "appliedSequence": -1,
            "pendingSince": datetime.now(UTC),
            "updatedAt": datetime.now(UTC),
        }
    )

    assert client.get("/health/ready").json() == {"status": "ready"}


def test_readiness_rejects_missing_search_worker_heartbeat(client: TestClient) -> None:
    client.app.state.database.search_worker_state.delete_many({})

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Search catalog unavailable"}


def test_readiness_rejects_stale_search_worker_heartbeat(client: TestClient) -> None:
    stale = datetime.now(UTC) - timedelta(seconds=11)
    client.app.state.database.search_worker_state.update_one(
        {"_id": "catalog"},
        {"$set": {"updatedAt": stale}},
        upsert=True,
    )

    assert client.get("/health/ready").status_code == 503


def test_production_rejects_demo_seed() -> None:
    with pytest.raises(ValueError, match="生产环境不能启用演示数据"):
        Settings(app_environment="production", enable_demo_seed=True)


def test_production_rejects_insecure_session_cookie() -> None:
    with pytest.raises(ValueError, match="生产环境必须启用 Secure Cookie"):
        Settings(app_environment="production", session_cookie_secure=False)


def test_mongo_pool_capacity_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "250")
    settings = Settings.from_environment()
    client, _database = connect(settings)

    assert client.options.pool_options.max_pool_size == 250
    client.close()


def test_search_catalog_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "SEARCH_URL": "http://meilisearch:7700",
        "SEARCH_INDEX_UID": "catalog-test",
        "SEARCH_API_KEY_FILE": "/run/secrets/meili-key",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.from_environment()

    assert settings.search_url == values["SEARCH_URL"]
    assert settings.search_index_uid == values["SEARCH_INDEX_UID"]
    assert settings.search_api_key_file == values["SEARCH_API_KEY_FILE"]


class ReadyReader:
    def health(self, _uid: str) -> CatalogHealth:
        return CatalogHealth(True, "catalogId", "test-generation", "test-epoch")


def _configured_database():
    database = mongomock.MongoClient()["configured_search"]
    database.client.admin.command = lambda _name: {"isWritablePrimary": True}
    database.search_catalog_generation.insert_one(_catalog_generation())
    database.search_worker_state.insert_one(_worker_state())
    return database


def _catalog_generation() -> dict:
    return {
        "_id": "catalog",
        "generation": "test-generation",
        "indexUid": "catalog-generation-test",
        "indexEpoch": "test-epoch",
        "retiredIndexUids": [],
    }


def _worker_state() -> dict:
    return {
        "_id": "catalog",
        "worker": "test-worker",
        "updatedAt": datetime.now(UTC),
    }


def configured_search_app(tmp_path, monkeypatch):
    key_file = tmp_path / "meili-key"
    key_file.write_text("test-key", encoding="utf-8")
    monkeypatch.setattr("app.main.create_reader", lambda _url, _file: ReadyReader())
    database = _configured_database()
    settings = Settings(
        app_environment="test",
        session_cookie_secure=False,
        search_api_key_file=str(key_file),
    )
    state = ReadyCatalogState(database)
    return create_app(database, settings, MemoryBlobStore(), catalog_state=state)


def test_application_builds_configured_search_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    with TestClient(configured_search_app(tmp_path, monkeypatch)) as configured:
        assert configured.get("/health/ready").json() == {"status": "ready"}
