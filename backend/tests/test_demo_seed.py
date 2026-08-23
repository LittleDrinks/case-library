from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import mongomock
import pytest
from pymongo.errors import DuplicateKeyError

from app.core.database import initialize
from app.modules.auth.seed import DEMO_ACCOUNTS, _insert_user, seed_demo_users
from app.modules.auth.service import authenticate
from app.modules.cases.seed import SEED_PATH, seed_demo_cases
from app.modules.cases.service import case_view


def test_user_ids_are_unique() -> None:
    database = mongomock.MongoClient()["unique_user_ids"]
    database.client.admin.command = lambda _name: {"ok": 1}
    initialize(database)
    database.users.insert_one({"id": "u-duplicate", "username": "first"})

    with pytest.raises(DuplicateKeyError):
        database.users.insert_one({"id": "u-duplicate", "username": "second"})


def test_demo_user_seed_is_concurrency_safe() -> None:
    database = mongomock.MongoClient()["concurrent_seed"]
    database.client.admin.command = lambda _name: {"ok": 1}
    initialize(database)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _index: seed_demo_users(database), range(8)))

    assert database.users.count_documents({}) == len(DEMO_ACCOUNTS)


def test_demo_seed_accepts_only_the_same_concurrent_insert(monkeypatch) -> None:
    database = mongomock.MongoClient()["concurrent_insert"]
    expected = {"id": "u-admin-demo", "username": "admin"}
    database.users.insert_one(expected)

    def collide(*_args, **_kwargs):
        raise DuplicateKeyError("race")

    monkeypatch.setattr(database.users, "update_one", collide)

    _insert_user(database, expected)

    with pytest.raises(DuplicateKeyError):
        _insert_user(database, {"id": "different", "username": "admin"})


def test_demo_accounts_match_the_approved_roster() -> None:
    by_username = {row["username"]: row for row in DEMO_ACCOUNTS}
    assert set(by_username) == {"admin", "user", "10000001", "10000002", "10000003"}
    assert by_username["10000001"]["name"] == "小杨"
    assert by_username["10000002"]["role"] == "admin"
    assert by_username["10000003"]["status"] == "disabled"


def test_disabled_demo_account_cannot_authenticate() -> None:
    database = mongomock.MongoClient()["account_status"]
    seed_demo_users(database)

    active = authenticate(database, "10000001", "Demo-10000001-2026!")
    disabled = authenticate(database, "10000003", "Demo-10000003-2026!")

    assert active and active["name"] == "小杨"
    assert disabled is None


def test_demo_case_seed_uses_the_current_schema_directly() -> None:
    seeds = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert all(set(seed) <= {"case", "version"} for seed in seeds)

    database = mongomock.MongoClient()["case_seed"]
    seed_demo_cases(database)

    assert database.cases.count_documents({}) == 6
    assert database.case_versions.count_documents({}) == 5
    assert database.cases.count_documents({"status": {"$exists": True}}) == 0
    draft = case_view(database.cases.find_one({"id": "c-draft-1"}))
    assert (draft["course"], draft["typeName"]) == ("自然辩证法概论", "思想实验类")
