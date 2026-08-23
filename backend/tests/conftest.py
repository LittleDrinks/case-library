from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.search.meilisearch import (
    CatalogKey,
    CatalogMetadata,
    CatalogPage,
    SearchUnavailable,
)
from app.modules.search.outbox import CatalogTarget
from app.modules.search.state import CatalogSnapshot


class MemoryBlobStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def health(self) -> None:
        return None

    def put(self, blob_id, source, length, _content_type) -> None:
        self.objects[blob_id] = source.read(length)

    def open(self, blob_id):
        return iter((self.objects[blob_id],))

    def remove(self, blob_id) -> None:
        self.objects.pop(blob_id, None)


class EmptySearchCatalog:
    def health(
        self, index_uid: str, expected_generation: str, expected_epoch: str
    ) -> None:
        assert (index_uid, expected_generation, expected_epoch) == (
            "catalog-generation-test",
            "test-generation",
            "test-epoch",
        )

    def search(self, request) -> CatalogPage:
        metadata = None
        if request.include_metadata:
            metadata = CatalogMetadata(
                0,
                {
                    "all": 0,
                    "case": 0,
                    "knowledge": 0,
                    "material": 0,
                },
                {},
            )
        return CatalogPage([], metadata, False, request.offset > 0)


class ReadyCatalogState:
    def __init__(self, database) -> None:
        self.database = database

    def read(self) -> CatalogSnapshot:
        marker = self.database.search_catalog_generation.find_one({"_id": "catalog"})
        if not marker or self._unavailable():
            raise SearchUnavailable("检索目录正在同步")
        target = CatalogTarget(
            marker["generation"],
            marker["indexUid"],
            marker["indexEpoch"],
        )
        control = self.database.search_control.find_one({"_id": "catalog"}) or {}
        rows = list(
            self.database.search_revocations.find({}, {"logicalKey": 1}).limit(101)
        )
        if len(rows) > 100:
            raise SearchUnavailable("检索目录正在同步")
        keys = tuple(CatalogKey(*row["logicalKey"].split(":", 1)) for row in rows)
        return CatalogSnapshot(target, int(control.get("sequence", 0)), keys)

    def _unavailable(self) -> bool:
        now = datetime.now(UTC).replace(tzinfo=None)
        state = self.database.search_catalog_state.find_one({"_id": "catalog"})
        if state and state.get("leaseExpiresAt", now) > now:
            return True
        worker = self.database.search_worker_state.find_one({"_id": "catalog"})
        if not worker or worker["updatedAt"] <= now - timedelta(seconds=10):
            return True
        return self._stale_outbox(now)

    def _stale_outbox(self, now: datetime) -> bool:
        for row in self.database.search_outbox.find({}):
            pending = row.get("sequence", -1) > row.get("appliedSequence", -1)
            if pending and row.get("pendingSince", now) <= now - timedelta(seconds=10):
                return True
        return False


class PassthroughSession:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def with_transaction(self, callback):
        return callback(None)


def _test_database():
    database = mongomock.MongoClient()["case_library_test"]
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
    database.client.admin.command = lambda _name: {"ok": 1, "isWritablePrimary": True}
    database.client.start_session = lambda: PassthroughSession()
    return database


@pytest.fixture(autouse=True)
def require_e2e_environment(request) -> None:
    marker = request.node.get_closest_marker("e2e")
    if not marker:
        return
    missing = [name for name in marker.args if not os.environ.get(name)]
    if missing:
        pytest.fail(f"missing E2E environment: {', '.join(missing)}", pytrace=False)


@pytest.fixture
def client(tmp_path) -> TestClient:
    database = _test_database()
    secret = tmp_path / "app-secret"
    secret.write_text("test-app-secret", encoding="utf-8")
    settings = Settings(
        app_environment="test",
        enable_demo_seed=True,
        session_cookie_secure=False,
        app_secret_file=str(secret),
    )
    app = create_app(
        database=database,
        settings=settings,
        blob_store=MemoryBlobStore(),
        search_catalog=EmptySearchCatalog(),
        catalog_state=ReadyCatalogState(database),
    )
    with TestClient(app) as test_client:
        yield test_client
