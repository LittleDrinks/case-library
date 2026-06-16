#!/usr/bin/env python3
"""Read-only MongoDB smoke checks for the case library."""

import sys
from pathlib import Path
from pprint import pprint

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from database import get_all_cases, get_db, get_mongo_client, serialize_case

COLLECTIONS = ["users", "cases", "reviews", "versions", "deployments"]


def find_duplicate_values(collection_name: str, field_name: str):
    pipeline = [
        {"$match": {field_name: {"$ne": None}}},
        {"$group": {"_id": f"${field_name}", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 10},
    ]
    return list(get_db()[collection_name].aggregate(pipeline))


def main():
    client = get_mongo_client()
    client.admin.command("ping")
    db = get_db()
    print("MongoDB connection: OK")

    print("\nCollection counts")
    for name in COLLECTIONS:
        print(f"{name}: {db[name].count_documents({})}")

    duplicate_case_ids = find_duplicate_values("cases", "id")
    duplicate_usernames = find_duplicate_values("users", "username")
    print(f"\nDuplicate cases.id entries: {len(duplicate_case_ids)}")
    if duplicate_case_ids:
        pprint(duplicate_case_ids)

    print(f"Duplicate users.username entries: {len(duplicate_usernames)}")
    if duplicate_usernames:
        pprint(duplicate_usernames)

    sample = db.cases.find_one({"status": {"$ne": "deleted"}})
    print("\nSample case serialization")
    if sample:
        serialized = serialize_case(sample)
        pprint(
            {
                "id": serialized.get("id"),
                "_id_type": type(serialized.get("_id")).__name__,
                "created_at_type": type(serialized.get("created_at")).__name__,
                "keywords_type": type(serialized.get("keywords")).__name__,
                "is_approved_type": type(serialized.get("is_approved")).__name__,
            }
        )
    else:
        print("No non-deleted case found.")

    listed = get_all_cases(status="all", limit=200)
    deleted_in_list = [case.get("id") for case in listed if case.get("status") == "deleted"]
    print(f"\nDeleted cases returned by normal list: {len(deleted_in_list)}")
    if deleted_in_list:
        print(f"Unexpected deleted case ids: {deleted_in_list[:10]}")

    if duplicate_case_ids or duplicate_usernames or deleted_in_list:
        raise SystemExit(1)

    print("\nSmoke checks passed.")


if __name__ == "__main__":
    main()
