"""Datetime normalization for Mongo documents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.db.constants import BEIJING_TZ, DATETIME_FIELDS


def normalize_to_beijing_datetime(value: Any) -> Any:
    """Normalize datetime-like values to a naive UTC+8 wall-clock datetime.

    PyMongo reads BSON dates as naive UTC datetimes by default. Plain strings
    without timezone metadata are treated as already being Beijing wall time.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(BEIJING_TZ).replace(tzinfo=None)
        return value.replace(tzinfo=UTC).astimezone(BEIJING_TZ).replace(tzinfo=None)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value

        parse_text = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(parse_text)
        except ValueError:
            parsed = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return value

        if parsed is None:
            return value
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return normalize_to_beijing_datetime(parsed)
        return parsed.replace(tzinfo=None)

    return value

def format_beijing_datetime(value: Any) -> Any:
    normalized = normalize_to_beijing_datetime(value)
    if isinstance(normalized, datetime):
        return normalized.strftime("%Y-%m-%d %H:%M:%S")
    return normalized

def _normalize_datetime_fields(doc: dict[str, Any]) -> dict[str, Any]:
    for field in DATETIME_FIELDS:
        if field in doc:
            doc[field] = format_beijing_datetime(doc[field])
    return doc

def serialize_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_beijing_datetime(value)
    return value
