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
        "created_at": 1,
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
        "created_at": 2,
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
        "created_at": 3,
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
    def __init__(self, rows: list[dict], versions: list[dict] | None = None):
        self.rows = rows
        self.versions = versions or []
        self.queries: list[dict] = []
        self.cursor: _FakeCursor | None = None
        self.pipelines: list[list[dict]] = []

    def find(self, query):
        self.queries.append(query)
        visible = [
            row
            for row in self.rows
            if row.get("status") == query.get("status") and row.get("is_hidden") is not True
        ]
        self.cursor = _FakeCursor(visible)
        return self.cursor

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        rows = [dict(row) for row in self.rows]
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
                for field in public.PUBLIC_REVIEW_SNAPSHOT_FIELDS:
                    if field in version:
                        row[field] = version[field]
            row["engagement_score"] = int(row.get("view_count") or 0) + int(row.get("like_count") or 0)

        for stage in pipeline:
            if "$match" in stage:
                rows = [row for row in rows if _matches(row, stage["$match"])]
            elif "$sort" in stage:
                sort_items = list(stage["$sort"].items())
                for field, direction in reversed(sort_items):
                    if isinstance(direction, dict) and direction.get("$meta") == "textScore":
                        rows.sort(key=lambda row: row.get(field) or 0, reverse=True)
                    else:
                        rows.sort(key=lambda row: row.get(field) or 0, reverse=direction == -1)
            elif "$skip" in stage:
                rows = rows[stage["$skip"]:]
            elif "$limit" in stage:
                rows = rows[:stage["$limit"]]
        return rows


class _FakeDb:
    def __init__(self, rows: list[dict], versions: list[dict] | None = None):
        self.cases = _FakeCases(rows, versions)


def _matches(row: dict, query: dict) -> bool:
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(row, option) for option in expected):
                return False
            continue
        if key == "$text":
            needle = str(expected.get("$search", "")).strip().lower()
            if not needle:
                continue
            searchable = [
                str(row.get("title") or ""),
                str(row.get("content") or ""),
                str(row.get("source_material") or ""),
                " ".join(str(value) for value in row.get("keywords") or []),
            ]
            if not any(needle == token.lower() for value in searchable for token in value.split()):
                return False
            row["public_text_score"] = sum(
                token.lower() == needle for value in searchable for token in value.split()
            )
            continue
        actual = row.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$regex" in expected and expected["$regex"].lower() not in str(actual).lower():
                return False
        elif actual != expected:
            return False
    return True


def _patch_public_cases(rows: list[dict]):
    old_query_cases = public._public_query_cases
    public._public_query_cases = (
        lambda match_filters=None, sort=None, skip=None, limit=None, text_query=None: _query_rows(
            rows,
            match_filters=match_filters,
            sort=sort,
            skip=skip,
            limit=limit,
            text_query=text_query,
        )
    )
    return old_query_cases


def _query_rows(
    rows: list[dict],
    *,
    match_filters: list[dict] | None = None,
    sort: dict | None = None,
    skip: int | None = None,
    limit: int | None = None,
    text_query: str | None = None,
):
    matches = []
    for row in rows:
        item = dict(row)
        item["engagement_score"] = int(item.get("view_count") or 0) + int(item.get("like_count") or 0)
        matches.append(item)
    if text_query and text_query.strip():
        text_filter = public._public_text_filter(text_query)
        matches = [row for row in matches if _matches(row, text_filter)]
    for match_filter in match_filters or []:
        matches = [row for row in matches if _matches(row, match_filter)]
    if sort:
        for field, direction in reversed(list(sort.items())):
            matches.sort(key=lambda row: row.get(field) or 0, reverse=direction == -1)
    start = max(0, int(skip or 0))
    bounded = public._bounded_limit(limit) if limit is not None else None
    return matches[start:] if bounded is None else matches[start:start + bounded]


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
        assert [item["id"] for item in public.search_cases("劳动", limit=1)] == [3]
        assert [item["id"] for item in public.search_cases("劳动", limit=5, offset=1)] == [1]
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


def test_public_search_uses_text_pipeline_before_regex_fallback():
    fake_db = _FakeDb(
        [
            {
                "id": 21,
                "title": "Labor policy",
                "content": "labor labor classroom",
                "source_material": "",
                "keywords": ["policy"],
                "status": "approved",
                "created_at": 21,
            },
            {
                "id": 22,
                "title": "Classroom labor",
                "content": "community",
                "source_material": "",
                "keywords": ["labor"],
                "status": "approved",
                "created_at": 22,
            },
        ]
    )
    old_get_db = public.get_db
    try:
        public.get_db = lambda: fake_db
        assert [item["id"] for item in public.search_cases("labor", limit=5)] == [21, 22]
    finally:
        public.get_db = old_get_db

    assert len(fake_db.cases.pipelines) == 1
    pipeline = fake_db.cases.pipelines[0]
    assert pipeline[0]["$match"] == {
        "status": "approved",
        "is_hidden": {"$ne": True},
        "$text": {"$search": "labor"},
    }
    assert {"$match": public._public_keyword_filter("labor")} in pipeline
    assert pipeline[-5:] == [
        {"$addFields": {"public_text_score": {"$meta": "textScore"}}},
        {"$match": public._public_keyword_filter("labor")},
        {"$sort": {"public_text_score": {"$meta": "textScore"}, "created_at": -1}},
        {"$skip": 0},
        {"$limit": 5},
    ]


def test_public_text_filter_quotes_multi_word_queries():
    assert public._public_text_filter("approved snapshot") == {
        "$text": {"$search": '"approved snapshot"'}
    }
    assert public._public_text_filter('approved "snapshot"') == {
        "$text": {"$search": '"approved \\"snapshot\\""'}
    }


def test_public_search_falls_back_to_regex_for_chinese_substrings():
    fake_db = _FakeDb(PUBLIC_CASES)
    old_get_db = public.get_db
    try:
        public.get_db = lambda: fake_db
        assert [item["id"] for item in public.search_cases("劳", limit=5)] == [3, 1]
    finally:
        public.get_db = old_get_db

    assert len(fake_db.cases.pipelines) == 2
    text_pipeline, fallback_pipeline = fake_db.cases.pipelines
    assert text_pipeline[0]["$match"]["$text"] == {"$search": "劳"}
    assert {"$match": public._public_keyword_filter("劳")} in fallback_pipeline
    assert fallback_pipeline[-3:] == [
        {"$sort": {"created_at": -1}},
        {"$skip": 0},
        {"$limit": 5},
    ]


def test_public_search_keeps_chinese_regex_results_when_text_has_partial_match():
    rows = [
        {
            "id": 23,
            "title": "劳动 课程",
            "content": "",
            "source_material": "",
            "keywords": [],
            "status": "approved",
            "created_at": 23,
        },
        {
            "id": 24,
            "title": "劳动教育",
            "content": "",
            "source_material": "",
            "keywords": [],
            "status": "approved",
            "created_at": 24,
        },
    ]
    fake_db = _FakeDb(rows)
    old_get_db = public.get_db
    try:
        public.get_db = lambda: fake_db
        assert [item["id"] for item in public.search_cases("劳动", limit=5)] == [24, 23]
    finally:
        public.get_db = old_get_db

    assert len(fake_db.cases.pipelines) == 2
    text_pipeline, fallback_pipeline = fake_db.cases.pipelines
    assert text_pipeline[0]["$match"]["$text"] == {"$search": "劳动"}
    assert {"$match": public._public_keyword_filter("劳动")} in fallback_pipeline


def test_public_filter_keyword_uses_text_first_with_type_theme_and_rejects_non_public_status():
    rows = [
        {
            "id": 31,
            "title": "labor plan",
            "type": "实践教学",
            "theme": "劳动",
            "content": "labor activity",
            "source_material": "",
            "keywords": ["labor"],
            "status": "approved",
            "created_at": 31,
        },
        {
            "id": 32,
            "title": "labor draft",
            "type": "实践教学",
            "theme": "劳动",
            "content": "labor activity",
            "source_material": "",
            "keywords": ["labor"],
            "status": "draft",
            "created_at": 32,
        },
        {
            "id": 33,
            "title": "labor other theme",
            "type": "实践教学",
            "theme": "法治",
            "content": "labor activity",
            "source_material": "",
            "keywords": ["labor"],
            "status": "approved",
            "created_at": 33,
        },
    ]
    fake_db = _FakeDb(rows)
    old_get_db = public.get_db
    try:
        public.get_db = lambda: fake_db
        assert [
            item["id"]
            for item in public.filter_cases(
                type_filter="实践教学",
                theme_filter="劳动",
                keyword_filter="labor",
                status_filter="approved",
                limit=5,
            )
        ] == [31]
        assert public.filter_cases(keyword_filter="labor", status_filter="draft") == []
    finally:
        public.get_db = old_get_db

    assert len(fake_db.cases.pipelines) == 1
    pipeline = fake_db.cases.pipelines[0]
    assert pipeline[0]["$match"] == {
        "status": "approved",
        "is_hidden": {"$ne": True},
        "$text": {"$search": "labor"},
    }
    assert {"$match": {"type": "实践教学"}} in pipeline
    assert {"$match": {"theme": "劳动"}} in pipeline
    assert {"$match": public._public_keyword_filter("labor")} in pipeline


def test_public_query_cases_uses_lookup_filters_skip_limit_and_snapshot_fields():
    rows = [
        {
            "id": 10,
            "title": "live title",
            "type": "LIVE_TYPE",
            "theme": "live-theme",
            "content": "live content",
            "source_material": "live source",
            "keywords": ["live-keyword"],
            "status": "approved",
            "is_hidden": False,
            "reviewed_version_id": 88,
            "created_at": 10,
        },
        {
            "id": 11,
            "title": "hidden public case",
            "status": "approved",
            "is_hidden": True,
            "created_at": 11,
        },
        {
            "id": 12,
            "title": "draft case",
            "status": "draft",
            "created_at": 12,
        },
    ]
    versions = [
        {
            "id": 88,
            "case_id": 10,
            "title": "reviewed title",
            "type": "REVIEWED_TYPE",
            "theme": "reviewed-theme",
            "content": "reviewed content",
            "source_material": "reviewed source",
            "keywords": ["reviewed-keyword"],
        }
    ]
    fake_db = _FakeDb(rows, versions)
    old_get_db = public.get_db
    try:
        public.get_db = lambda: fake_db
        result = public._public_query_cases(
            match_filters=[{"type": "REVIEWED_TYPE"}],
            sort={"created_at": -1},
            skip=0,
            limit=1,
        )
    finally:
        public.get_db = old_get_db

    assert [item["id"] for item in result] == [10]
    assert result[0]["title"] == "reviewed title"
    assert result[0]["content"] == "reviewed content"
    assert result[0]["source_material"] == "reviewed source"
    assert result[0]["keywords"] == ["reviewed-keyword"]

    pipeline = fake_db.cases.pipelines[-1]
    assert pipeline[0] == {"$match": {"status": "approved", "is_hidden": {"$ne": True}}}
    assert any("$lookup" in stage and stage["$lookup"]["from"] == "versions" for stage in pipeline)
    assert any("$unwind" in stage for stage in pipeline)
    assert {"$match": {"type": "REVIEWED_TYPE"}} in pipeline
    assert pipeline[-3:] == [{"$sort": {"created_at": -1}}, {"$skip": 0}, {"$limit": 1}]


def test_public_search_fallback_builds_snapshot_keyword_pipeline_before_pagination():
    fake_db = _FakeDb([])
    old_get_db = public.get_db
    try:
        public.get_db = lambda: fake_db
        assert public.search_cases("reviewed-keyword", limit=3, offset=2) == []
    finally:
        public.get_db = old_get_db

    pipeline = fake_db.cases.pipelines[-1]
    match_stages = [stage["$match"] for stage in pipeline if "$match" in stage]
    assert match_stages[0] == {"status": "approved", "is_hidden": {"$ne": True}}
    assert match_stages[1] == public._public_keyword_filter("reviewed-keyword")
    assert pipeline[-3:] == [{"$sort": {"created_at": -1}}, {"$skip": 2}, {"$limit": 3}]


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
        public._public_query_cases = old_query_cases

        rows = [
            {"id": 4, "status": "approved", "is_hidden": False, "created_at": 4},
            {"id": 7, "status": "approved", "created_at": 7},
            {"id": 5, "status": "draft", "is_hidden": False, "created_at": 5},
            {"id": 6, "status": "approved", "is_hidden": True, "created_at": 6},
        ]
        fake_db = _FakeDb(rows)
        public.get_db = lambda: fake_db
        assert [item["id"] for item in public.get_latest_cases(limit=1)] == [7]
        pipeline = fake_db.cases.pipelines[-1]
        assert pipeline[0] == {"$match": {"status": "approved", "is_hidden": {"$ne": True}}}
        assert pipeline[-2:] == [{"$sort": {"created_at": -1}}, {"$limit": 1}]
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
    test_public_search_uses_text_pipeline_before_regex_fallback()
    test_public_text_filter_quotes_multi_word_queries()
    test_public_search_falls_back_to_regex_for_chinese_substrings()
    test_public_search_keeps_chinese_regex_results_when_text_has_partial_match()
    test_public_filter_keyword_uses_text_first_with_type_theme_and_rejects_non_public_status()
    test_public_query_cases_uses_lookup_filters_skip_limit_and_snapshot_fields()
    test_public_search_fallback_builds_snapshot_keyword_pipeline_before_pagination()
    test_public_recommendations_trending_and_latest_use_public_cases_only()
    print("public search helper unit checks passed")


if __name__ == "__main__":
    main()
