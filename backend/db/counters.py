"""Integer id counter helpers."""

from __future__ import annotations

from pymongo import DESCENDING, ReturnDocument

from backend.db.connection import get_db
from backend.db.constants import COUNTER_COLLECTIONS
from backend.db.datetime import _normalize_datetime_fields


def _max_legacy_id(collection_name: str) -> int:
    doc = get_db()[collection_name].find_one(
        {"id": {"$type": "number"}},
        sort=[("id", DESCENDING)],
        projection={"id": 1},
    )
    return int(doc["id"]) if doc and doc.get("id") is not None else 0

def sync_counter(collection_name: str):
    """Make a counter at least as large as the current maximum legacy id."""
    if collection_name not in COUNTER_COLLECTIONS:
        raise ValueError(f"Unknown counter collection: {collection_name}")

    max_id = _max_legacy_id(collection_name)
    get_db().counters.update_one(
        {"_id": collection_name},
        {"$max": {"seq": max_id}},
        upsert=True,
    )

def sync_all_counters():
    for collection_name in COUNTER_COLLECTIONS:
        sync_counter(collection_name)

def next_sequence(collection_name: str) -> int:
    """Atomically allocate the next integer id for a collection."""
    sync_counter(collection_name)
    result = get_db().counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if not result or "seq" not in result:
        raise RuntimeError(f"Unable to allocate id for {collection_name}")
    return int(result["seq"])

def _insert_with_generated_id(collection_name: str, doc: dict) -> int:
    doc["id"] = next_sequence(collection_name)
    _normalize_datetime_fields(doc)
    result = get_db()[collection_name].insert_one(doc)
    if not result.acknowledged:
        raise RuntimeError(f"Insert into {collection_name} was not acknowledged")
    return int(doc["id"])
