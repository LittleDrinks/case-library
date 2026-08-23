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
