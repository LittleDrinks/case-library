from __future__ import annotations

from datetime import UTC, datetime

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from conftest import EmptySearchCatalog, ReadyCatalogState

DEMO_ACCOUNT_IDS = (
    "u-admin-demo",
    "u-user-demo",
    "u-roster-yang",
    "u-roster-li",
    "u-roster-zhao",
)


def _database():
    database = mongomock.MongoClient()["production_startup_test"]
    database.client.admin.command = lambda _name: {"ok": 1, "isWritablePrimary": True}
    database.search_catalog_generation.insert_one(
        {
            "_id": "catalog",
            "generation": "test-generation",
            "indexUid": "catalog-generation-test",
            "indexEpoch": "test-epoch",
            "retiredIndexUids": [],
        }
    )
    database.search_worker_state.insert_one(
        {
            "_id": "catalog",
            "worker": "test-worker",
            "updatedAt": datetime.now(UTC),
        }
    )
    return database


def _settings() -> Settings:
    return Settings(app_environment="production", session_cookie_secure=True)


def _app(database):
    class ReadyBlobStore:
        def health(self) -> None:
            return None

    return create_app(
        database=database,
        settings=_settings(),
        blob_store=ReadyBlobStore(),
        search_catalog=EmptySearchCatalog(),
        catalog_state=ReadyCatalogState(database),
    )


@pytest.mark.parametrize("account_id", DEMO_ACCOUNT_IDS)
def test_production_startup_rejects_published_seed_accounts(account_id: str) -> None:
    database = _database()
    account = {"id": account_id, "username": "any-name", "marker": "unchanged"}
    database.users.insert_one(dict(account))

    with pytest.raises(RuntimeError, match="生产环境数据库包含演示账号"):
        with TestClient(_app(database)):
            pass

    assert database.users.find_one({"id": account["id"]}, {"_id": 0}) == account


@pytest.mark.parametrize("account", [None, {"id": "u-production", "username": "admin"}])
def test_production_startup_accepts_fresh_or_production_database(account) -> None:
    database = _database()
    if account:
        database.users.insert_one(dict(account))

    with TestClient(_app(database)) as client:
        assert client.get("/health/ready").json() == {"status": "ready"}
