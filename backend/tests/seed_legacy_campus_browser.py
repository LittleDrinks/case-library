from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from pymongo import MongoClient

from app.modules.auth.passwords import hash_password


PREFIX = "issue360-legacy-browser"


def _database():
    client = MongoClient(os.environ["AUTH_QUERY_MONGODB_URI"], serverSelectionTimeoutMS=5000)
    return client, client.get_default_database()


def seed(database) -> None:
    database.users.delete_many({"username": {"$regex": f"^{PREFIX}-"}})
    password_hash = hash_password("synthetic-legacy-fixture-password-2026")
    now = datetime.now(UTC).isoformat()
    database.users.insert_many([
        {
            "id": f"u-{PREFIX}-{number:03d}",
            "username": f"{PREFIX}-{number:03d}",
            "name": f"{PREFIX}-{number:03d}",
            "password_hash": password_hash,
            "role": "user",
            "status": "active",
            "must_change_password": False,
            "campus_verified": True,
            "campus_access_grant_source": "legacy",
            "token_version": 0,
            "createdAt": now,
            "updatedAt": now,
        }
        for number in range(1, 52)
    ])


def cleanup(database) -> None:
    database.users.delete_many({"username": {"$regex": f"^{PREFIX}-"}})


def main() -> None:
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command not in {"seed", "cleanup"}:
        raise SystemExit("usage: seed_legacy_campus_browser.py seed|cleanup")
    client, database = _database()
    try:
        (seed if command == "seed" else cleanup)(database)
    finally:
        client.close()


if __name__ == "__main__":
    main()
