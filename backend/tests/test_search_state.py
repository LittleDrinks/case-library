from __future__ import annotations

from copy import deepcopy

import pytest

from app.modules.search.meilisearch import CatalogKey, SearchUnavailable
from app.modules.search.outbox import CatalogTarget
from app.modules.search.state import MongoCatalogState


class AggregateCollection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows, self.calls, self.read_concern = rows, [], None

    def with_options(self, *, read_concern):
        self.read_concern = read_concern
        return self

    def aggregate(self, pipeline: list[dict]):
        self.calls.append(pipeline)
        return iter(deepcopy(self.rows))


class Database:
    def __init__(self, rows: list[dict]) -> None:
        self.search_catalog_generation = AggregateCollection(rows)


def _row() -> dict:
    return {
        "generation": "generation-1",
        "indexUid": "catalog-generation-1",
        "indexEpoch": "2026-08-14T00:00:00Z",
        "control": [{"sequence": 7}],
        "rebuild": [],
        "worker": [{"_id": "catalog"}],
        "stale": [],
        "revocations": [{"logicalKey": "case:c-1"}],
    }


def test_snapshot_uses_one_aggregate_and_parses_catalog_state() -> None:
    database = Database([_row()])

    snapshot = MongoCatalogState(database).read()

    assert snapshot.target == CatalogTarget(
        "generation-1",
        "catalog-generation-1",
        "2026-08-14T00:00:00Z",
    )
    assert snapshot.sequence == 7
    assert snapshot.revoked_keys == (CatalogKey("case", "c-1"),)
    assert len(database.search_catalog_generation.calls) == 1
    assert database.search_catalog_generation.read_concern.level == "snapshot"


def _changed(**changes) -> list[dict]:
    row = _row()
    row.update(changes)
    return [row]


@pytest.mark.parametrize(
    "rows",
    [
        [],
        _changed(rebuild=[{}]),
        _changed(worker=[]),
        _changed(stale=[{}]),
        _changed(
            revocations=[{"logicalKey": f"case:c-{index}"} for index in range(101)]
        ),
    ],
)
def test_snapshot_fails_closed_for_an_unsynchronized_catalog(rows: list[dict]) -> None:
    with pytest.raises(SearchUnavailable, match="检索目录正在同步"):
        MongoCatalogState(Database(rows)).read()


def test_snapshot_version_includes_sequence_and_physical_target() -> None:
    before = MongoCatalogState(Database([_row()])).read()
    after_row = _row()
    after_row["control"] = [{"sequence": 8}]
    after = MongoCatalogState(Database([after_row])).read()

    assert before.same_version(before)
    assert not before.same_version(after)
