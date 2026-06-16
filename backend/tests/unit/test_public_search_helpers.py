#!/usr/bin/env python3
"""Unit checks for public search helpers and the search engine facade."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ["MONGODB_DB_NAME"] = f"case_library_public_unit_{uuid4().hex[:8]}"

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import search_engine
from repositories import cases
from services import public

PUBLIC_CASES = [
    {
        "id": 1,
        "title": "劳动教育案例",
        "type": "实践教学",
        "theme": "劳动",
        "content": "学生参加社区服务",
        "source_material": "访谈记录",
        "keywords": ["志愿服务", "劳动"],
        "view_count": 5,
        "like_count": 2,
        "status": "approved",
    },
    {
        "id": 2,
        "title": "法治课堂",
        "type": "课堂教学",
        "theme": "法治",
        "content": "案例讨论",
        "source_material": "法院公开材料",
        "keywords": ["宪法"],
        "view_count": 1,
        "like_count": 9,
        "status": "approved",
    },
    {
        "id": 3,
        "title": "劳动主题延伸",
        "type": "实践教学",
        "theme": "劳动",
        "content": "校内实践",
        "source_material": "课程材料",
        "keywords": ["实践"],
        "view_count": 3,
        "like_count": 0,
        "status": "approved",
    },
]


class _FakeCursor:
    def __init__(self, rows: list[dict]):
        self.rows = list(rows)
        self.query = None
        self.sort_args = None
        self.limit_value = None

    def sort(self, *args):
        self.sort_args = args
        if len(args) == 2:
            field, direction = args
            self.rows.sort(key=lambda row: row.get(field), reverse=direction == -1)
        return self

    def limit(self, value):
        self.limit_value = value
        self.rows = self.rows[:value]
        return self

    def __iter__(self):
        return iter(self.rows)


class _FakeCases:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.queries: list[dict] = []
        self.cursor: _FakeCursor | None = None

    def find(self, query):
        self.queries.append(query)
        visible = [
            row
            for row in self.rows
            if row.get("status") == query.get("status") and row.get("is_hidden") is not True
        ]
        self.cursor = _FakeCursor(visible)
        return self.cursor


class _FakeDb:
    def __init__(self, rows: list[dict]):
        self.cases = _FakeCases(rows)


def _patch_public_cases(rows: list[dict]):
    old_query_cases = public._public_query_cases
    public._public_query_cases = lambda: list(rows)
    return old_query_cases


def test_case_search_engine_forwards_arguments():
    calls = []
    old_search = search_engine.search_cases
    old_recommend = search_engine.get_recommendation_candidates
    old_trending = search_engine.get_trending_cases
    old_latest = search_engine.get_latest_cases
    old_filter = search_engine.filter_cases
    try:
        search_engine.search_cases = lambda query, status, limit: calls.append(
            ("search", query, status, limit)
        ) or ["search-result"]
        search_engine.get_recommendation_candidates = lambda case_id, limit: calls.append(
            ("recommend", case_id, limit)
        ) or ["recommend-result"]
        search_engine.get_trending_cases = lambda limit: calls.append(
            ("trending", limit)
        ) or ["trending-result"]
        search_engine.get_latest_cases = lambda limit: calls.append(
            ("latest", limit)
        ) or ["latest-result"]
        search_engine.filter_cases = (
            lambda type_filter, theme_filter, status_filter, keyword_filter, limit: calls.append(
                ("filter", type_filter, theme_filter, status_filter, keyword_filter, limit)
            )
            or ["filter-result"]
        )

        engine = search_engine.CaseSearchEngine()
        assert engine.search("劳动", status="approved_all", limit=7) == ["search-result"]
        assert engine.get_recommendations(42, limit=3) == ["recommend-result"]
        assert engine.get_trending(limit=4) == ["trending-result"]
        assert engine.get_latest(limit=6) == ["latest-result"]
        assert engine.advanced_filter("实践教学", "劳动", "approved", "志愿", 8) == [
            "filter-result"
        ]
    finally:
        search_engine.search_cases = old_search
        search_engine.get_recommendation_candidates = old_recommend
        search_engine.get_trending_cases = old_trending
        search_engine.get_latest_cases = old_latest
        search_engine.filter_cases = old_filter

    assert calls == [
        ("search", "劳动", "approved_all", 7),
        ("recommend", 42, 3),
        ("trending", 4),
        ("latest", 6),
        ("filter", "实践教学", "劳动", "approved", "志愿", 8),
    ]


def test_public_status_filter_rejects_non_public_statuses():
    assert public._status_search_filter(None) == {"status": "approved"}
    assert public._status_search_filter("all") == {"status": "approved"}
    assert public._status_search_filter("approved_all") == {"status": "approved"}
    for status in ("draft", "pending_review", "rejected", "needs_revision"):
        assert public._status_search_filter(status) == {"status": "__public_search_no_match__"}


def test_public_field_matches_title_content_source_and_keywords():
    item = {
        "title": "标题里的劳动",
        "content": "正文包含社区服务",
        "source_material": "访谈记录",
        "keywords": ["思政", "实践"],
    }
    assert public._public_field_matches(item, "劳动")
    assert public._public_field_matches(item, "社区")
    assert public._public_field_matches(item, "访谈")
    assert public._public_field_matches(item, "实践")
    assert public._public_field_matches(item, "  ")
    assert not public._public_field_matches(item, "法治")


def test_public_search_and_filter_apply_status_offset_limit_and_filters():
    old_query_cases = _patch_public_cases(PUBLIC_CASES)
    try:
        assert [item["id"] for item in public.search_cases("劳动", limit=1)] == [1]
        assert [item["id"] for item in public.search_cases("劳动", limit=5, offset=1)] == [3]
        assert public.search_cases("劳动", status="pending_review") == []
        assert public.search_cases("  ") == []

        filtered = public.filter_cases(
            type_filter="实践教学",
            theme_filter="劳动",
            keyword_filter="实践",
            limit=5,
        )
        assert [item["id"] for item in filtered] == [3]
        assert public.filter_cases(status_filter="draft") == []
        assert [item["id"] for item in public.filter_cases(limit=1, offset=1)] == [2]
    finally:
        public._public_query_cases = old_query_cases


def test_public_recommendations_trending_and_latest_use_public_cases_only():
    old_query_cases = _patch_public_cases(PUBLIC_CASES)
    old_serialize_public_case = public.serialize_public_case
    old_get_db = public.get_db
    old_get_case = cases.get_case
    try:
        public.serialize_public_case = lambda row: row if row and row.get("status") == "approved" else None
        cases.get_case = lambda case_id: next(
            (item for item in PUBLIC_CASES if item.get("id") == int(case_id)),
            None,
        )

        assert [item["id"] for item in public.get_recommendation_candidates(1, limit=5)] == [3]
        assert [item["id"] for item in public.get_trending_cases(limit=2)] == [2, 1]

        rows = [
            {"id": 4, "status": "approved", "is_hidden": False, "created_at": 4},
            {"id": 7, "status": "approved", "created_at": 7},
            {"id": 5, "status": "draft", "is_hidden": False, "created_at": 5},
            {"id": 6, "status": "approved", "is_hidden": True, "created_at": 6},
        ]
        fake_db = _FakeDb(rows)
        public.get_db = lambda: fake_db
        assert [item["id"] for item in public.get_latest_cases(limit=1)] == [7]
        assert fake_db.cases.queries == [{"status": "approved", "is_hidden": {"$ne": True}}]
        assert fake_db.cases.cursor is not None
        assert fake_db.cases.cursor.limit_value == 1
    finally:
        public._public_query_cases = old_query_cases
        public.serialize_public_case = old_serialize_public_case
        public.get_db = old_get_db
        cases.get_case = old_get_case


def main() -> None:
    test_case_search_engine_forwards_arguments()
    test_public_status_filter_rejects_non_public_statuses()
    test_public_field_matches_title_content_source_and_keywords()
    test_public_search_and_filter_apply_status_offset_limit_and_filters()
    test_public_recommendations_trending_and_latest_use_public_cases_only()
    print("public search helper unit checks passed")


if __name__ == "__main__":
    main()
