#!/usr/bin/env python3
"""Unit checks for database repository helpers."""

# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ["MONGODB_DB_NAME"] = f"case_library_test_repo_unit_{uuid4().hex[:8]}"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from backend.db.constants import PUBLIC_REVIEW_SNAPSHOT_FIELDS
from backend.db.transactions import multi_collection_write
from backend.repositories import cases, users
from backend.services import abuse


class _FakeUsers:
    def __init__(self, docs: dict[str, dict]):
        self.docs = docs
        self.queries: list[dict] = []

    def find_one(self, query, projection=None):
        self.queries.append(query)
        return self.docs.get(query.get("username"))


class _FakeCursor:
    def __init__(self, rows: list[dict]):
        self.rows = list(rows)
        self.sort_args = None
        self.skip_value = None
        self.limit_value = None

    def sort(self, *args):
        self.sort_args = args
        return self

    def skip(self, value):
        self.skip_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        self.rows = self.rows[:value]
        return self

    def __iter__(self):
        return iter(self.rows)


class _FakeCases:
    def __init__(self, rows: list[dict], versions: list[dict] | None = None):
        self.rows = rows
        self.versions = versions or []
        self.find_calls: list[tuple[dict, dict | None]] = []
        self.aggregate_calls: list[list[dict]] = []
        self.cursor: _FakeCursor | None = None

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        rows = list(self.rows)
        if projection:
            rows = [
                {key: value for key, value in row.items() if projection.get(key)}
                for row in rows
            ]
        self.cursor = _FakeCursor(rows)
        return self.cursor

    def aggregate(self, pipeline):
        self.aggregate_calls.append(pipeline)
        rows = [dict(row) for row in self.rows]
        for stage in pipeline:
            if "$match" in stage:
                rows = [row for row in rows if _matches(row, stage["$match"])]
            elif "$lookup" in stage:
                for row in rows:
                    version = next(
                        (
                            item
                            for item in self.versions
                            if item.get("id") == row.get("reviewed_version_id")
                            and item.get("case_id") == row.get("id")
                        ),
                        None,
                    )
                    if version:
                        row["reviewed_version"] = dict(version)
            elif "$addFields" in stage:
                add_fields = stage["$addFields"]
                if "engagement_score" in add_fields:
                    for row in rows:
                        row["engagement_score"] = int(row.get("view_count") or 0) + int(
                            row.get("like_count") or 0
                        )
                else:
                    for row in rows:
                        version = row.get("reviewed_version") or {}
                        for field in PUBLIC_REVIEW_SNAPSHOT_FIELDS:
                            if field in version:
                                row[field] = version[field]
            elif "$sort" in stage:
                for field, direction in reversed(list(stage["$sort"].items())):
                    rows.sort(key=lambda row: row.get(field) or 0, reverse=direction == -1)
            elif "$skip" in stage:
                rows = rows[stage["$skip"]:]
            elif "$limit" in stage:
                rows = rows[: stage["$limit"]]
        return rows


class _FakeVersions:
    def __init__(self):
        self.find_one_calls: list[dict] = []

    def find_one(self, query):
        self.find_one_calls.append(query)
        raise AssertionError("public list must not perform per-row version lookups")


class _FakeDb:
    def __init__(
        self,
        user_docs: dict[str, dict],
        case_rows: list[dict] | None = None,
        version_rows: list[dict] | None = None,
    ):
        self.users = _FakeUsers(user_docs)
        self.cases = _FakeCases(case_rows or [], version_rows)
        self.versions = _FakeVersions()


def _matches(row: dict, query: dict) -> bool:
    for key, expected in query.items():
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$nin" in expected and actual in expected["$nin"]:
                return False
        elif actual != expected:
            return False
    return True


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


def test_case_filter_and_keyword_diff_helpers():
    current = {"keywords": ["劳动", "", "思政"]}
    assert not cases._values_differ("keywords", current, '["劳动", "思政"]')
    assert cases._values_differ("keywords", current, ["劳动", "法治"])
    assert cases._values_differ("title", {"title": "旧标题"}, "新标题")


def test_case_lists_use_projection_and_omit_large_fields():
    rows = [
        {
            "id": 1,
            "title": "列表案例",
            "type": "TYPE_A",
            "theme": "主题",
            "content": "large content",
            "source_material": "large source",
            "author": "alice",
            "department": "dept",
            "status": "approved",
            "created_at": "2020-01-01 08:00:00",
            "updated_at": "2020-01-02 08:00:00",
            "submitted_at": "2020-01-03 08:00:00",
            "view_count": 2,
            "like_count": 3,
            "keywords": ["关键词"],
            "reviewed_version_id": 44,
        }
    ]
    versions = [
        {
            "id": 44,
            "case_id": 1,
            "title": "审核快照标题",
            "type": "SNAPSHOT_TYPE",
            "theme": "审核主题",
            "author": "reviewer-author",
            "department": "review-dept",
            "keywords": ["审核关键词"],
            "content": "reviewed content",
            "source_material": "reviewed source",
        }
    ]
    fake_db = _FakeDb({}, rows, versions)
    old_get_db = cases.get_db
    try:
        cases.get_db = lambda: fake_db

        internal_items = cases.get_all_cases(status="approved", limit=5)
        assert fake_db.cases.find_calls[0][1] == cases.CASE_LIST_PROJECTION
        assert "content" not in internal_items[0]
        assert "source_material" not in internal_items[0]
        assert internal_items[0]["title"] == "列表案例"

        public_items = cases.get_all_public_cases(status="approved", limit=5)
        assert len(fake_db.cases.find_calls) == 1
        assert fake_db.versions.find_one_calls == []
        pipeline = fake_db.cases.aggregate_calls[-1]
        assert pipeline[0] == {"$match": {"status": "approved", "is_hidden": {"$ne": True}}}
        assert any("$lookup" in stage and stage["$lookup"]["from"] == "versions" for stage in pipeline)
        assert "content" not in public_items[0]
        assert "source_material" not in public_items[0]
        assert public_items[0]["title"] == "审核快照标题"
        assert public_items[0]["type"] == "SNAPSHOT_TYPE"
        assert public_items[0]["theme"] == "审核主题"
        assert public_items[0]["author"] == "reviewer-author"
        assert public_items[0]["department"] == "review-dept"
        assert public_items[0]["keywords"] == ["审核关键词"]
    finally:
        cases.get_db = old_get_db

    assert "content" not in cases.CASE_LIST_PROJECTION
    assert "source_material" not in cases.CASE_LIST_PROJECTION
    assert "content" not in cases.PUBLIC_CASE_LIST_PROJECTION
    assert "source_material" not in cases.PUBLIC_CASE_LIST_PROJECTION


def test_serialize_user_doc_normalizes_defaults_but_public_hides_secrets():
    password_hash = users.hash_password("password123")
    raw_user = {
        "id": 1,
        "username": "alice",
        "password": password_hash,
        "role": "user",
        "token_version": "bad",
    }

    serialized = users._serialize_user_doc(raw_user)
    assert serialized is not None
    assert serialized["role"] == "normal"
    assert serialized["nickname"] == ""
    assert serialized["status"] == "active"
    assert serialized["must_change_password"] is False
    assert serialized["token_version"] == 0
    assert serialized["password"] == password_hash

    public_user = users.serialize_user_public(raw_user)
    assert public_user is not None
    assert public_user["username"] == "alice"
    assert "password" not in public_user
    assert "token_version" not in public_user


def test_verify_password_returns_false_for_bad_hashes():
    assert users.verify_password("password123", "not-a-bcrypt-hash") is False
    assert users.verify_password("", users.hash_password("password123")) is False
    assert users.verify_password("password123", "") is False


def test_multi_collection_write_runs_compensations_on_error_in_reverse_order():
    events = []
    try:
        with multi_collection_write("unit-test") as scope:
            scope.compensate_with(lambda: events.append("first"))
            scope.compensate_with(lambda: events.append("second"))
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert events == ["second", "first"]

    with multi_collection_write("unit-test-commit") as scope:
        scope.compensate_with(lambda: events.append("committed"))
    assert events == ["second", "first"]


def test_public_interaction_identity_hashes_request_headers_without_secrets():
    identity = abuse.public_interaction_identity(
        headers={
            "X-Forwarded-For": "203.0.113.10, 10.0.0.1",
            "User-Agent": "unit-test",
        }
    )
    assert identity.source == "request"
    assert identity.key != "203.0.113.10|unit-test"
    assert len(identity.key) == 64

    assert abuse.public_interaction_identity(headers={}).key == "anonymous"


def test_public_interaction_rate_limiter_defaults_to_permissive_and_can_block():
    identity = abuse.PublicInteractionIdentity("unit")
    limiter = abuse.FixedWindowRateLimiter()
    assert limiter.allow("case.like", identity)
    assert limiter.allow("case.like", identity)

    limiter = abuse.FixedWindowRateLimiter(max_events=1, window_seconds=60)
    assert limiter.allow("case.like", identity)
    assert not limiter.allow("case.like", identity)


def main() -> None:
    test_case_list_filter_author_alias_status_hidden_and_deleted()
    test_case_filter_and_keyword_diff_helpers()
    test_case_lists_use_projection_and_omit_large_fields()
    test_serialize_user_doc_normalizes_defaults_but_public_hides_secrets()
    test_verify_password_returns_false_for_bad_hashes()
    test_multi_collection_write_runs_compensations_on_error_in_reverse_order()
    test_public_interaction_identity_hashes_request_headers_without_secrets()
    test_public_interaction_rate_limiter_defaults_to_permissive_and_can_block()
    print("database repository helper unit checks passed")


if __name__ == "__main__":
    main()
