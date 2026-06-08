#!/usr/bin/env python3
"""Create or normalize deterministic accounts for browser E2E tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from database import create_user, get_user_by_username, init_db, set_user_password, update_user_fields


ACCOUNTS = [
    {
        "username": "e2e_user",
        "password": "E2eUserPass123!",
        "role": "normal",
        "nickname": "E2E作者",
        "must_change_password": False,
        "status": "active",
    },
    {
        "username": "e2e_admin",
        "password": "E2eAdminPass123!",
        "role": "admin",
        "nickname": "E2E管理员",
        "must_change_password": False,
        "status": "active",
    },
    {
        "username": "10000002",
        "password": "default123456",
        "role": "admin",
        "nickname": "小李",
        "must_change_password": True,
        "status": "active",
    },
]


def upsert_account(account: dict) -> None:
    existing = get_user_by_username(account["username"])
    if existing:
        update_user_fields(
            account["username"],
            role=account["role"],
            nickname=account["nickname"],
            status=account["status"],
        )
        set_user_password(
            account["username"],
            account["password"],
            must_change_password=account["must_change_password"],
        )
        print(f"Updated account: {account['username']}")
        return

    create_user(**account)
    print(f"Created account: {account['username']}")


def main() -> None:
    init_db()
    for account in ACCOUNTS:
        upsert_account(account)


if __name__ == "__main__":
    main()
