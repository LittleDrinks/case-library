from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pymongo import MongoClient

from app.modules.search.meilisearch import CatalogKey, SearchUnavailable
from app.modules.search.state import MongoCatalogState

pytestmark = pytest.mark.e2e("SEARCH_CURSOR_MONGODB_URI")
NOW = datetime(2026, 9, 20, tzinfo=UTC)


@pytest.fixture
def catalog_database():
    client = MongoClient(os.environ["SEARCH_CURSOR_MONGODB_URI"])
    name = f"case_library_test_catalog_{uuid4().hex}"
    database = client[name]
    try:
        database.search_catalog_generation.insert_one({
            "_id": "catalog", "generation": "g-1",
            "indexUid": "catalog-g-1", "indexEpoch": "epoch-1",
        })
        database.search_control.insert_one({"_id": "catalog", "sequence": 7})
        database.search_worker_state.insert_one({"_id": "catalog", "updatedAt": NOW})
        yield database
    finally:
        client.drop_database(name)
        client.close()


def read_catalog(database):
    return MongoCatalogState(database, clock=lambda: NOW).read()


def assert_availability(database, available):
    if available:
        assert read_catalog(database).target.generation == "g-1"
    else:
        with pytest.raises(SearchUnavailable, match="检索目录正在同步"):
            read_catalog(database)


@pytest.mark.parametrize("age_ms,available", [(9999, True), (10000, False), (10001, False)])
def test_catalog_requires_a_worker_heartbeat_younger_than_ten_seconds(
    catalog_database, age_ms, available,
):
    catalog_database.search_worker_state.update_one(
        {"_id": "catalog"}, {"$set": {"updatedAt": NOW - timedelta(milliseconds=age_ms)}},
    )
    assert_availability(catalog_database, available)


@pytest.mark.parametrize("lease_ms,available", [(-1, True), (0, True), (1, False)])
def test_catalog_blocks_only_while_rebuild_lease_is_active(
    catalog_database, lease_ms, available,
):
    catalog_database.search_catalog_state.insert_one({
        "_id": "catalog", "leaseExpiresAt": NOW + timedelta(milliseconds=lease_ms),
    })
    assert_availability(catalog_database, available)


@pytest.mark.parametrize("age_ms,sequence,applied,available", [
    (9999, 8, 7, True), (10000, 8, 7, False), (10001, 8, 7, False),
    (10000, 7, 7, True), (10000, 6, 7, True),
])
def test_catalog_blocks_old_unapplied_changes_but_allows_recent_or_applied_changes(
    catalog_database, age_ms, sequence, applied, available,
):
    catalog_database.search_outbox.insert_one({
        "_id": "case:c-1", "pendingSince": NOW - timedelta(milliseconds=age_ms),
        "sequence": sequence, "appliedSequence": applied,
    })
    assert_availability(catalog_database, available)


@pytest.mark.parametrize("count", [0, 1, 100, 101])
def test_catalog_returns_every_revocation_or_fails_closed_above_the_limit(
    catalog_database, count,
):
    if count:
        catalog_database.search_revocations.insert_many([
            {"logicalKey": f"case:c-{index}"} for index in range(count)
        ])
    if count > 100:
        assert_availability(catalog_database, False)
    else:
        snapshot = read_catalog(catalog_database)
        assert set(snapshot.revoked_keys) == {CatalogKey("case", f"c-{i}") for i in range(count)}
        assert snapshot.sequence == 7


def test_catalog_ignores_unrelated_generation_control_and_rebuild_rows(catalog_database):
    generation = catalog_database.search_catalog_generation.find_one({"_id": "catalog"})
    catalog_database.search_catalog_generation.delete_one({"_id": "catalog"})
    catalog_database.search_catalog_generation.insert_one({
        "_id": "other", "generation": "wrong", "indexUid": "wrong", "indexEpoch": "wrong",
    })
    catalog_database.search_catalog_generation.insert_one(generation)
    catalog_database.search_control.delete_one({"_id": "catalog"})
    catalog_database.search_control.insert_many([
        {"_id": "other", "sequence": 99}, {"_id": "catalog", "sequence": 7},
    ])
    catalog_database.search_catalog_state.insert_one({
        "_id": "other", "leaseExpiresAt": NOW + timedelta(days=1),
    })
    snapshot = read_catalog(catalog_database)
    assert snapshot.sequence == 7
    assert (snapshot.target.generation, snapshot.target.index_uid, snapshot.target.index_epoch) == (
        "g-1", "catalog-g-1", "epoch-1",
    )


def test_unrelated_worker_cannot_make_the_catalog_ready(catalog_database):
    catalog_database.search_worker_state.delete_one({"_id": "catalog"})
    catalog_database.search_worker_state.insert_one({"_id": "other", "updatedAt": NOW})
    assert_availability(catalog_database, False)
