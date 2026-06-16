#!/usr/bin/env python3
"""Unit checks for database compatibility exports and repository helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ["MONGODB_DB_NAME"] = f"case_library_repo_unit_{uuid4().hex[:8]}"

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import database
from repositories import cases, users


class _FakeUsers:
    def __init__(self, docs: dict[str, dict]):
        self.docs = docs
        self.queries: list[dict] = []

    def find_one(self, query, projection=None):
        self.queries.append(query)
        return self.docs.get(query.get("username"))


class _FakeDb:
    def __init__(self, user_docs: dict[str, dict]):
        self.users = _FakeUsers(user_docs)


def test_case_list_filter_author_alias_status_hidden_and_deleted():
    fake_db = _FakeDb({"alice": {"username": "alice", "nickname": "Alice Teacher"}})
    old_get_db = cases.get_db
    try:
        cases.get_db = lambda: fake_db

        query = cases._case_list_filter(status="all", author="alice", include_hidden=False)
        assert query["$or"][0] == {"owner_username": "alice"}
        assert set(query["$or"][1]["author"]["$in"]) == {"alice", "Alice Teacher"}
        assert set(query["status"]["$nin"]) == {"draft", "deleted"}
        assert query["is_hidden"] == {"$ne": True}

        assert cases._case_list_filter(status="rejected")["status"] == "needs_revision"
        assert cases._case_list_filter(status="approved_all")["status"] == "approved"

        deleted_query = cases._case_list_filter(status="deleted", include_deleted=False)
        assert deleted_query["status"] == {"$ne": "deleted"}

        include_hidden_query = cases._case_list_filter(status="approved", include_hidden=True)
        assert "is_hidden" not in include_hidden_query
    finally:
        cases.get_db = old_get_db

    assert fake_db.users.queries == [{"username": "alice"}]


def test_database_compat_exports_case_filter_and_keyword_diff_helpers():
    assert database._case_list_filter is cases._case_list_filter
    assert database._values_differ is cases._values_differ

    current = {"keywords": ["劳动", "", "思政"]}
    assert not database._values_differ("keywords", current, '["劳动", "思政"]')
    assert database._values_differ("keywords", current, ["劳动", "法治"])
    assert database._values_differ("title", {"title": "旧标题"}, "新标题")


def test_serialize_user_doc_normalizes_defaults_but_public_hides_secrets():
    password_hash = users.hash_password("password123")
    raw_user = {
        "id": 1,
        "username": "alice",
        "password": password_hash,
        "role": "user",
        "token_version": "bad",
    }

    serialized = database._serialize_user_doc(raw_user)
    assert serialized is not None
    assert serialized["role"] == "normal"
    assert serialized["nickname"] == ""
    assert serialized["status"] == "active"
    assert serialized["must_change_password"] is False
    assert serialized["token_version"] == 0
    assert serialized["password"] == password_hash

    public_user = database.serialize_user_public(raw_user)
    assert public_user is not None
    assert public_user["username"] == "alice"
    assert "password" not in public_user
    assert "token_version" not in public_user


def test_verify_password_returns_false_for_bad_hashes():
    assert database.verify_password("password123", "not-a-bcrypt-hash") is False
    assert database.verify_password("", users.hash_password("password123")) is False
    assert database.verify_password("password123", "") is False


def main() -> None:
    test_case_list_filter_author_alias_status_hidden_and_deleted()
    test_database_compat_exports_case_filter_and_keyword_diff_helpers()
    test_serialize_user_doc_normalizes_defaults_but_public_hides_secrets()
    test_verify_password_returns_false_for_bad_hashes()
    print("database repository helper unit checks passed")


if __name__ == "__main__":
    main()
