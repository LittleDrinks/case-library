"""Pure review-domain helpers with no database side effects."""

from __future__ import annotations

import json
from typing import Any

COMMENT_CATEGORIES = {"source", "fact", "structure", "classification", "classroom", "clarity"}
COMMENT_SEVERITIES = {"info", "suggestion", "important"}
PARAGRAPH_ID_KEYS = ("paragraph_id", "paragraphId", "paragraphID", "paragraph")


def split_paragraphs(content: str) -> list[dict[str, str]]:
    paragraphs: list[dict[str, str]] = []
    for line in str(content or "").splitlines():
        text = line.strip()
        if not text:
            continue
        paragraphs.append({"paragraph_id": f"p{len(paragraphs) + 1}", "text": text})
    if not paragraphs and str(content or "").strip():
        paragraphs.append({"paragraph_id": "p1", "text": str(content).strip()})
    return paragraphs


def _normalize_summary(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        value = {}
    summary: dict[str, list[str]] = {}
    for key in ("strengths", "risks", "suggested_next_steps"):
        items = value.get(key, [])
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            items = []
        summary[key] = [str(item) for item in items if item is not None and str(item).strip()]
    return summary


def normalize_paragraph_comments(value: Any, paragraph_ids: set[str] | None = None) -> list[dict]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("paragraph_comments must be valid JSON") from exc
    if not isinstance(value, list):
        raise ValueError("paragraph_comments must be a list")

    normalized: list[dict[str, Any]] = []
    allowed_ids = paragraph_ids or set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError("paragraph_comments records must be objects")
        paragraph_id = ""
        for key in PARAGRAPH_ID_KEYS:
            if key in item:
                paragraph_id = str(item.get(key, "")).strip()
                break
        if not paragraph_id:
            raise ValueError("paragraph_comments records require paragraph_id")
        if allowed_ids and paragraph_id not in allowed_ids:
            raise ValueError(f"Unknown paragraph_id: {paragraph_id}")

        category = str(item.get("category", "clarity")).strip()
        if category not in COMMENT_CATEGORIES:
            category = "clarity"
        severity = str(item.get("severity", "suggestion")).strip()
        if severity not in COMMENT_SEVERITIES:
            severity = "suggestion"
        message = str(item.get("message", "")).strip()
        if not message:
            raise ValueError("paragraph_comments records require message")

        normalized.append(
            {
                "id": str(item.get("id") or f"c{index + 1}"),
                "paragraph_id": paragraph_id,
                "quote": str(item.get("quote", ""))[:500],
                "category": category,
                "severity": severity,
                "message": message,
                "suggestion": str(item.get("suggestion", "")).strip(),
            }
        )
    return normalized


def normalize_structured_ai_review(value: Any, paragraph_ids: set[str]) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("AI review JSON parse failed") from exc
    if not isinstance(value, dict):
        raise ValueError("AI review result must be a JSON object")

    comments = normalize_paragraph_comments(value.get("comments", []), paragraph_ids)
    return {"comments": comments, "summary": _normalize_summary(value.get("summary", {}))}


__all__ = [
    "COMMENT_CATEGORIES",
    "COMMENT_SEVERITIES",
    "PARAGRAPH_ID_KEYS",
    "normalize_paragraph_comments",
    "normalize_structured_ai_review",
    "split_paragraphs",
]
