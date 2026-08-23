from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pymongo.read_concern import ReadConcern

from app.modules.search.meilisearch import CatalogKey, SearchUnavailable
from app.modules.search.outbox import CatalogTarget

MAX_REVOCATIONS = 100
SYNC_LAG = timedelta(seconds=10)


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    target: CatalogTarget
    sequence: int
    revoked_keys: tuple[CatalogKey, ...]

    def same_version(self, other: CatalogSnapshot) -> bool:
        return self.target == other.target and self.sequence == other.sequence


def _lookup(collection: str, pipeline: list[dict], name: str) -> dict:
    return {"$lookup": {"from": collection, "pipeline": pipeline, "as": name}}


def _active_rebuild(now: datetime) -> list[dict]:
    return [
        {
            "$match": {
                "_id": "catalog",
                "leaseExpiresAt": {"$gt": now},
            }
        },
        {"$limit": 1},
    ]


def _fresh_worker(now: datetime) -> list[dict]:
    return [
        {
            "$match": {
                "_id": "catalog",
                "updatedAt": {"$gt": now - SYNC_LAG},
            }
        },
        {"$limit": 1},
    ]


def _stale_outbox(now: datetime) -> list[dict]:
    return [
        {
            "$match": {
                "pendingSince": {"$lte": now - SYNC_LAG},
                "sequence": {"$exists": True},
                "appliedSequence": {"$exists": True},
                "$expr": {"$gt": ["$sequence", "$appliedSequence"]},
            }
        },
        {"$limit": 1},
    ]


def _pipeline(now: datetime) -> list[dict]:
    catalog = [{"$match": {"_id": "catalog"}}, {"$limit": 1}]
    revoked = [{"$project": {"_id": 0, "logicalKey": 1}}, {"$limit": 101}]
    return [
        {"$match": {"_id": "catalog"}},
        _lookup("search_control", catalog, "control"),
        _lookup("search_catalog_state", _active_rebuild(now), "rebuild"),
        _lookup("search_worker_state", _fresh_worker(now), "worker"),
        _lookup("search_outbox", _stale_outbox(now), "stale"),
        _lookup("search_revocations", revoked, "revocations"),
        {"$project": {"_id": 0, "retiredIndexUids": 0}},
    ]


def _target(row: dict) -> CatalogTarget:
    fields = ("generation", "indexUid", "indexEpoch")
    if not all(row.get(field) for field in fields):
        raise SearchUnavailable("检索目录正在同步")
    return CatalogTarget(*(row[field] for field in fields))


def _revoked_keys(row: dict) -> tuple[CatalogKey, ...]:
    rows = row.get("revocations", [])
    if len(rows) > MAX_REVOCATIONS:
        raise SearchUnavailable("检索目录正在同步")
    return tuple(CatalogKey(*item["logicalKey"].split(":", 1)) for item in rows)


def _snapshot(row: dict | None) -> CatalogSnapshot:
    if not row or row.get("rebuild") or row.get("stale") or not row.get("worker"):
        raise SearchUnavailable("检索目录正在同步")
    control = row.get("control") or [{}]
    return CatalogSnapshot(
        _target(row), int(control[0].get("sequence", 0)), _revoked_keys(row)
    )


class MongoCatalogState:
    def __init__(self, database, clock=lambda: datetime.now(UTC)) -> None:
        collection = database.search_catalog_generation
        self._collection = collection.with_options(read_concern=ReadConcern("snapshot"))
        self._clock = clock

    def read(self) -> CatalogSnapshot:
        try:
            row = next(iter(self._collection.aggregate(_pipeline(self._clock()))), None)
            return _snapshot(row)
        except SearchUnavailable:
            raise
        except Exception as error:
            raise SearchUnavailable("检索目录正在同步") from error
