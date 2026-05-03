#!/usr/bin/env python3
"""Migrate SQLite data into MongoDB without deleting or overwriting data."""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

from database import SQLITE_DB_PATH, get_db, init_db, sync_all_counters


TABLES = ["users", "cases", "reviews", "versions", "deployments"]


def resolve_sqlite_path() -> Path:
    path = Path(os.getenv("SQLITE_DB_PATH", SQLITE_DB_PATH))
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path.resolve()


def connect_sqlite_readonly() -> sqlite3.Connection:
    sqlite_path = resolve_sqlite_path()
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def fetch_rows(conn: sqlite3.Connection, table_name: str) -> List[Dict]:
    if not has_table(conn, table_name):
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table_name}")]


def parse_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value

    text = str(value)
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def normalize_keywords(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None and str(item) != ""]
        except json.JSONDecodeError:
            pass
        return [value]
    return [str(value)]


def clean_doc(table_name: str, row: Dict) -> Dict:
    doc = dict(row)

    if table_name == "cases":
        doc["keywords"] = normalize_keywords(doc.get("keywords"))
        doc["is_approved"] = bool(doc.get("is_approved", 0))
        doc["is_in_library"] = bool(doc.get("is_in_library", 0))
        doc["view_count"] = int(doc.get("view_count") or 0)
        doc["like_count"] = int(doc.get("like_count") or 0)

    for field in ["created_at", "updated_at", "review_at", "deployed_at"]:
        if field in doc:
            parsed = parse_datetime(doc.get(field))
            if parsed is not None:
                doc[field] = parsed
            elif doc.get(field) in (None, ""):
                doc.pop(field, None)

    return doc


def migrate_collection(table_name: str, rows: Iterable[Dict]) -> Dict[str, int]:
    db = get_db()
    collection = db[table_name]
    total = 0
    inserted = 0
    skipped = 0
    errors = 0

    for row in rows:
        total += 1
        try:
            doc = clean_doc(table_name, row)
            legacy_id = doc.get("id")
            if legacy_id is None:
                print(f"[{table_name}] skip row without id: {row}")
                skipped += 1
                continue

            if collection.count_documents({"id": legacy_id}, limit=1) > 0:
                skipped += 1
                continue

            collection.insert_one(doc)
            inserted += 1
        except Exception as exc:
            errors += 1
            print(f"[{table_name}] failed to migrate id={row.get('id')}: {exc}")

    return {"sqlite": total, "inserted": inserted, "skipped": skipped, "errors": errors}


def main():
    init_db()
    sqlite_path = resolve_sqlite_path()
    print(f"Reading SQLite database in read-only mode: {sqlite_path}")

    conn = connect_sqlite_readonly()
    try:
        summaries = {}
        for table_name in TABLES:
            rows = fetch_rows(conn, table_name)
            summaries[table_name] = migrate_collection(table_name, rows)
    finally:
        conn.close()

    sync_all_counters()

    print("\nMigration summary")
    for table_name in TABLES:
        summary = summaries[table_name]
        print(
            f"{table_name}: SQLite={summary['sqlite']}, "
            f"inserted={summary['inserted']}, skipped={summary['skipped']}, "
            f"errors={summary['errors']}"
        )


if __name__ == "__main__":
    main()
