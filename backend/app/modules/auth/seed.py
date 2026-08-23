from __future__ import annotations

import csv
from pathlib import Path

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.modules.auth.passwords import hash_password

SEED_PATH = Path(__file__).resolve().parents[4] / "files" / "accounts.csv"


def _account(row: dict[str, str]) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "password": row["password"],
        "name": row["name"],
        "role": row["role"],
        "status": row["status"],
        "must_change_password": row["must_change_password"] == "true",
        "token_version": 0,
    }


def _read_accounts() -> tuple[dict, ...]:
    with SEED_PATH.open(encoding="utf-8", newline="") as source:
        return tuple(_account(row) for row in csv.DictReader(source))


DEMO_ACCOUNTS = _read_accounts()
DEMO_ACCOUNT_IDS = tuple(account["id"] for account in DEMO_ACCOUNTS)


def reject_demo_accounts(database: Database) -> None:
    if database.users.find_one({"id": {"$in": DEMO_ACCOUNT_IDS}}, {"_id": 1}):
        raise RuntimeError("生产环境数据库包含演示账号")


def _user(account: dict) -> dict:
    user = {key: value for key, value in account.items() if key != "password"}
    user["password_hash"] = hash_password(account["password"])
    return user


def _insert_user(database: Database, user: dict) -> None:
    try:
        database.users.update_one(
            {"username": user["username"]}, {"$setOnInsert": user}, upsert=True
        )
    except DuplicateKeyError:
        query = {"id": user["id"], "username": user["username"]}
        if not database.users.find_one(query, {"_id": 1}):
            raise


def seed_demo_users(database: Database) -> None:
    for account in DEMO_ACCOUNTS:
        _insert_user(database, _user(account))
