#!/usr/bin/env python3
"""Unit-level checks for backend contract helper behavior."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import database


def assert_public_payload(item: dict) -> None:
    forbidden = {
        "ai_reviews",
        "ai_review",
        "admin_comments",
        "paragraph_comments",
        "prompt",
        "prompt_id",
        "model",
        "latest_review_version_id",
        "submitted_version_id",
        "reviewed_version_id",
        "owner_username",
    }
    assert forbidden.isdisjoint(item), item


def assert_paragraph_contracts() -> None:
    paragraphs = database.split_paragraphs(" 第一段 \n\n第二段\n  第三段  ")
    assert paragraphs == [
        {"paragraph_id": "p1", "text": "第一段"},
        {"paragraph_id": "p2", "text": "第二段"},
        {"paragraph_id": "p3", "text": "第三段"},
    ]

    comments = database.normalize_paragraph_comments(
        [
            {
                "paragraph_id": "p1",
                "category": "unknown",
                "severity": "critical",
                "message": "  需要补充来源  ",
                "suggestion": " 增加材料 ",
                "quote": "x" * 600,
            }
        ],
        {"p1"},
    )
    assert comments == [
        {
            "id": "c1",
            "paragraph_id": "p1",
            "quote": "x" * 500,
            "category": "clarity",
            "severity": "suggestion",
            "message": "需要补充来源",
            "suggestion": "增加材料",
        }
    ]

    try:
        database.normalize_paragraph_comments(
            [{"paragraph_id": "p9", "message": "未知段落"}],
            {"p1"},
        )
    except ValueError as exc:
        assert "Unknown paragraph_id: p9" in str(exc)
    else:
        raise AssertionError("unknown paragraph_id should fail")


def assert_structured_ai_review_contract() -> None:
    review = database.normalize_structured_ai_review(
        {
            "comments": [{"paragraph_id": "p2", "message": "分类需要更准确"}],
            "summary": {
                "strengths": "结构清楚",
                "risks": ["分类偏宽", ""],
                "suggested_next_steps": None,
            },
        },
        {"p1", "p2"},
    )
    assert review["comments"][0]["paragraph_id"] == "p2"
    assert review["comments"][0]["category"] == "clarity"
    assert review["comments"][0]["severity"] == "suggestion"
    assert review["summary"] == {
        "strengths": ["结构清楚"],
        "risks": ["分类偏宽"],
        "suggested_next_steps": [],
    }


class _FakeVersions:
    def find_one(self, query: dict) -> dict | None:
        assert query == {"id": 44, "case_id": 7}
        return {
            "id": 44,
            "case_id": 7,
            "title": "审核通过标题",
            "type": "TYPE_APPROVED",
            "theme": "approved-theme",
            "content": "审核通过正文",
            "source_material": "审核通过来源材料",
            "author": "审核作者",
            "department": "审核院系",
            "keywords": ["审核关键词"],
            "owner_username": "owner",
            "ai_review": {"comments": []},
            "admin_comments": [{"comments": []}],
        }


class _FakeDb:
    versions = _FakeVersions()


def assert_public_serialization_uses_review_snapshot() -> None:
    original_get_db = database.get_db
    database.get_db = lambda: _FakeDb()
    try:
        public = database.serialize_public_case(
            {
                "id": 7,
                "title": "当前内部标题",
                "type": "TYPE_LIVE",
                "theme": "live-theme",
                "content": "当前内部正文",
                "source_material": "当前内部来源材料",
                "author": "当前作者",
                "department": "当前院系",
                "status": "approved",
                "created_at": "2020-01-01 08:00:00",
                "updated_at": "2020-01-02 08:00:00",
                "submitted_at": "2020-01-03 08:00:00",
                "reviewed_version_id": 44,
                "submitted_version_id": 43,
                "owner_username": "owner",
                "ai_reviews": [],
                "latest_review_version_id": 42,
            }
        )
    finally:
        database.get_db = original_get_db

    assert public["title"] == "审核通过标题"
    assert public["type"] == "TYPE_APPROVED"
    assert public["theme"] == "approved-theme"
    assert public["content"] == "审核通过正文"
    assert public["source_material"] == "审核通过来源材料"
    assert public["author"] == "审核作者"
    assert public["department"] == "审核院系"
    assert public["keywords"] == ["审核关键词"]
    assert public["display_at"] == "2020-01-03 08:00:00"
    assert_public_payload(public)


def main() -> None:
    database.MONGODB_DB_NAME = f"case_library_contract_unit_{uuid4().hex}"
    assert_paragraph_contracts()
    assert_structured_ai_review_contract()
    assert_public_serialization_uses_review_snapshot()
    print("contract helper unit checks passed")


if __name__ == "__main__":
    main()
