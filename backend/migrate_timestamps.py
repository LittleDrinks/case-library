#!/usr/bin/env python3
"""Explicit timestamp migration for UTC+8 storage.

This script converts configured timestamp fields to plain Beijing time strings
("YYYY-MM-DD HH:MM:SS"). It is intentionally not called by application startup.

Timezone rules:
- BSON datetime values read by PyMongo are treated as UTC instants and converted
  to UTC+8.
- Strings with an explicit timezone suffix, such as "Z" or "+00:00", are
  converted to UTC+8.
- Plain strings without timezone metadata are treated as already being local
  Beijing wall time and are not shifted again.

Before applying, take a database backup. The optional JSON backup created by
this script can restore the fields it changed, but it is not a substitute for a
full MongoDB backup.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import COUNTER_COLLECTIONS, DATETIME_FIELDS, format_beijing_datetime, get_db


def encode_backup_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return {"__type": "objectid", "value": str(value)}
    if isinstance(value, datetime):
        return {"__type": "datetime", "value": value.isoformat()}
    return value


def decode_backup_value(value: Any) -> Any:
    if isinstance(value, dict) and value.get("__type") == "datetime":
        return datetime.fromisoformat(value["value"])
    return value


def planned_changes() -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    exists_filter = {"$or": [{field: {"$exists": True}} for field in DATETIME_FIELDS]}
    projection = dict.fromkeys(DATETIME_FIELDS, 1)

    db = get_db()
    for collection_name in COUNTER_COLLECTIONS:
        collection = db[collection_name]
        for doc in collection.find(exists_filter, projection=projection):
            updates: dict[str, Any] = {}
            original: dict[str, Any] = {}
            for field in DATETIME_FIELDS:
                if field not in doc:
                    continue
                current = doc.get(field)
                normalized = format_beijing_datetime(current)
                if normalized != current:
                    original[field] = current
                    updates[field] = normalized
            if updates:
                changes.append(
                    {
                        "collection": collection_name,
                        "_id": doc["_id"],
                        "original": original,
                        "updates": updates,
                    }
                )
    return changes


def write_backup(changes: list[dict[str, Any]], backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "timezone": "BSON datetimes are treated as UTC; plain strings are treated as existing UTC+8 wall time.",
        "changes": [
            {
                "collection": item["collection"],
                "_id": str(item["_id"]),
                "original": {
                    key: encode_backup_value(value) for key, value in item["original"].items()
                },
            }
            for item in changes
        ],
    }
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_changes(changes: list[dict[str, Any]]) -> None:
    db = get_db()
    for item in changes:
        db[item["collection"]].update_one({"_id": item["_id"]}, {"$set": item["updates"]})


def restore_backup(backup_path: Path) -> int:
    payload = json.loads(backup_path.read_text(encoding="utf-8"))
    restored = 0
    db = get_db()
    for item in payload.get("changes", []):
        original = {
            key: decode_backup_value(value) for key, value in item.get("original", {}).items()
        }
        if not original:
            continue
        db[item["collection"]].update_one({"_id": ObjectId(item["_id"])}, {"$set": original})
        restored += 1
    return restored


def default_backup_path() -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path(__file__).resolve().parent.parent / "data" / f"timestamp_backup_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize timestamp fields to UTC+8 plain strings."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--backup", type=Path, default=None, help="Backup JSON path for apply mode."
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Apply without writing a JSON field backup."
    )
    parser.add_argument(
        "--restore",
        type=Path,
        help="Restore timestamp fields from a backup JSON created by this script.",
    )
    args = parser.parse_args()

    if args.restore:
        restored = restore_backup(args.restore)
        print(f"Restored timestamp fields on {restored} document(s) from {args.restore}")
        return 0

    changes = planned_changes()
    print("Timezone policy: BSON datetimes/offset strings -> UTC+8; plain strings stay unchanged.")
    print(f"Documents requiring timestamp updates: {len(changes)}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply after taking a MongoDB backup.")
        for item in changes[:20]:
            print(f"- {item['collection']} _id={item['_id']} updates={item['updates']}")
        if len(changes) > 20:
            print(f"... {len(changes) - 20} more change(s) omitted")
        return 0

    backup_path = args.backup or default_backup_path()
    if not args.no_backup:
        write_backup(changes, backup_path)
        print(f"Wrote field backup: {backup_path}")
        print(f"Rollback command: python backend/migrate_timestamps.py --restore {backup_path}")
    else:
        print("WARNING: applying without JSON field backup. Ensure a full MongoDB backup exists.")

    apply_changes(changes)
    print(f"Applied timestamp updates to {len(changes)} document(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
