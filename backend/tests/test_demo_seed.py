from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import mongomock
import pytest
from pymongo.errors import DuplicateKeyError

from app.core.database import _mark_legacy_campus_grant, initialize
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
    assert by_username["admin"]["campus_verified"] is True
    assert by_username["10000002"]["campus_verified"] is True
    assert by_username["10000003"]["campus_verified"] is False
    assert by_username["10000003"]["status"] == "disabled"


def test_auth_initialization_marks_explicit_legacy_grants_without_changing_access() -> None:
    database = mongomock.MongoClient()["legacy_campus_access_sources"]
    database.client.admin.command = lambda _name: {"ok": 1}
    initialize(database)
    database.users.insert_many(
        [
            {
                "id": "u-legacy-admin",
                "username": "legacy-admin",
                "role": "admin",
                "campus_verified": True,
            },
            {
                "id": "u-legacy-user",
                "username": "legacy-user",
                "role": "user",
                "campus_verified": True,
            },
            {
                "id": "u-unverified-admin",
                "username": "unverified-admin",
                "role": "admin",
                "campus_verified": False,
            },
        ]
    )

    initialize(database)

    admin = database.users.find_one({"id": "u-legacy-admin"})
    ordinary = database.users.find_one({"id": "u-legacy-user"})
    unverified_admin = database.users.find_one({"id": "u-unverified-admin"})
    assert admin["campus_verified"] is True
    assert admin["campus_access_grant_source"] == "legacy"
    assert ordinary["campus_verified"] is True
    assert ordinary["campus_access_grant_source"] == "legacy"
    assert unverified_admin["campus_verified"] is False
    assert "campus_access_grant_source" not in unverified_admin
    assert database.campus_access_applications.count_documents({}) == 0


def test_auth_initialization_preserves_application_source_and_revoked_legacy_grant() -> None:
    database = mongomock.MongoClient()["campus_access_migration_restart"]
    database.client.admin.command = lambda _name: {"ok": 1}
    initialize(database)
    database.users.insert_many([
        {
            "id": "u-promoted-admin", "username": "promoted-admin", "role": "admin",
            "campus_verified": True,
        },
        {
            "id": "u-approved-admin", "username": "approved-admin", "role": "admin",
            "campus_verified": True,
            "campus_access_grant_source": "application",
            "campus_access_granted_by_application_id": "ca-approved-admin",
        },
    ])

    initialize(database)
    legacy = database.users.find_one({"id": "u-promoted-admin"})
    assert legacy["campus_verified"] is True
    assert legacy["campus_access_grant_source"] == "legacy"
    database.users.update_one(
        {"id": "u-promoted-admin"},
        {"$set": {"campus_verified": False, "campus_access_revoked_at": "revoked"}},
    )
    initialize(database)
    revoked = database.users.find_one({"id": "u-promoted-admin"})
    approved = database.users.find_one({"id": "u-approved-admin"})
    assert revoked["campus_verified"] is False
    assert revoked["campus_access_revoked_at"] == "revoked"
    assert revoked["campus_access_grant_source"] == "legacy"
    assert approved["campus_verified"] is True
    assert approved["campus_access_grant_source"] == "application"


def test_stale_legacy_source_marker_cannot_restore_revoked_or_replace_application_grant() -> None:
    database = mongomock.MongoClient()["campus_access_marker_race"]
    database.users.insert_many([
        {
            "id": "u-revoked-legacy", "username": "revoked-legacy", "role": "admin",
            "campus_verified": True,
        },
        {
            "id": "u-new-approval", "username": "new-approval", "role": "user",
            "campus_verified": True,
        },
    ])
    stale_revoked = database.users.find_one({"id": "u-revoked-legacy"})
    stale_approved = database.users.find_one({"id": "u-new-approval"})
    database.users.update_one(
        {"id": "u-revoked-legacy"},
        {"$set": {
            "campus_verified": False,
            "campus_access_grant_source": "legacy",
            "campus_access_revoked_at": "synthetic-revoked-at",
        }},
    )
    database.users.update_one(
        {"id": "u-new-approval"},
        {"$set": {
            "campus_verified": True,
            "campus_access_grant_source": "application",
            "campus_access_granted_by_application_id": "ca-synthetic-approval",
        }},
    )

    _mark_legacy_campus_grant(database, stale_revoked)
    _mark_legacy_campus_grant(database, stale_approved)

    revoked = database.users.find_one({"id": "u-revoked-legacy"})
    approved = database.users.find_one({"id": "u-new-approval"})
    assert revoked["campus_verified"] is False
    assert revoked["campus_access_grant_source"] == "legacy"
    assert revoked["campus_access_revoked_at"] == "synthetic-revoked-at"
    assert approved["campus_access_grant_source"] == "application"
    assert approved["campus_access_granted_by_application_id"] == "ca-synthetic-approval"



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
