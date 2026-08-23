from __future__ import annotations

import mongomock

from app.modules.search.worker import catalog_change


def test_hidden_case_deletes_every_acl_projection() -> None:
    database = mongomock.MongoClient()["case_change_test"]

    change = catalog_change(database, "case:c-hidden")

    assert change.documents == []
    assert change.deleted_ids == [
        "case-c-hidden-public",
        "case-c-hidden-campus",
        "case-c-hidden-private",
    ]
