from __future__ import annotations

import mongomock
import pytest
from pymongo.errors import WriteConcernError

from app.core import database as database_module
from app.core.database import initialize


def _keys(database, collection: str) -> set[tuple[tuple[str, int], ...]]:
    indexes = database[collection].index_information().values()
    return {tuple(index["key"]) for index in indexes}


def test_initialize_uses_business_material_indexes() -> None:
    database = mongomock.MongoClient()["database_indexes_test"]

    initialize(database)

    assert _keys(database, "materials") == {
        (("_id", 1),),
        (("id", 1),),
        (("status", 1), ("accessLevel", 1)),
    }


def test_initialize_indexes_catalog_delivery_state() -> None:
    database = mongomock.MongoClient()["database_indexes_test"]

    initialize(database)

    assert (("updatedAt", 1), ("_id", 1)) in _keys(database, "search_outbox")
    assert (("pendingSince", 1), ("_id", 1)) in _keys(database, "search_outbox")
    assert (("logicalKey", 1),) in _keys(database, "search_revocations")


def test_agent_indexes_match_current_optional_artifact_fields() -> None:
    database = mongomock.MongoClient()["database_indexes_test"]

    initialize(database)

    version_indexes = database.case_versions.index_information()
    assert version_indexes["one_ai_version_per_run"]["partialFilterExpression"] == {
        "sourceRunId": {"$type": "string"},
        "sourceArtifactId": None,
    }
    assert version_indexes["one_ai_version_per_artifact"]["partialFilterExpression"] == {
        "sourceArtifactId": {"$type": "string"},
    }

    write_indexes = database.agent_writes.index_information()
    assert write_indexes["runId_1"]["partialFilterExpression"] == {
        "artifactId": None,
    }
    assert write_indexes["one_write_per_artifact"]["partialFilterExpression"] == {
        "artifactId": {"$type": "string"},
    }
    assert "schema_migrations" not in database.list_collection_names()


def test_initialize_retries_only_replica_state_change_write_concern(
    monkeypatch,
) -> None:
    database = mongomock.MongoClient()["database_retry_test"]
    original = database_module._initialize_auth
    calls = 0

    def interrupt_once(target) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise WriteConcernError("operation interrupted", 11602)
        original(target)

    monkeypatch.setattr(database_module, "_initialize_auth", interrupt_once)
    monkeypatch.setattr(database_module.time, "sleep", lambda _seconds: None)

    initialize(database)

    assert calls == 2


def test_initialize_does_not_retry_other_write_concern_errors(monkeypatch) -> None:
    database = mongomock.MongoClient()["database_retry_test"]
    calls = 0

    def fail(target) -> None:
        nonlocal calls
        calls += 1
        raise WriteConcernError("write concern failed", 64)

    monkeypatch.setattr(database_module, "_initialize_auth", fail)
    monkeypatch.setattr(database_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(WriteConcernError, match="write concern failed"):
        initialize(database)

    assert calls == 1


def test_initialize_bounds_replica_state_change_retries(monkeypatch) -> None:
    database = mongomock.MongoClient()["database_retry_test"]
    calls = 0

    def keep_interrupted(_target) -> None:
        nonlocal calls
        calls += 1
        raise WriteConcernError("operation interrupted", 11602)

    monkeypatch.setattr(database_module, "_initialize_auth", keep_interrupted)
    monkeypatch.setattr(database_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(WriteConcernError, match="operation interrupted"):
        initialize(database)

    assert calls == 5
