from __future__ import annotations

import mongomock

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
