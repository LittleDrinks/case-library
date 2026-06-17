#!/usr/bin/env python3
"""Initialize default MongoDB accounts when the users collection is empty."""

# ruff: noqa: E402

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from backend.db.connection import init_db
from backend.repositories.users import create_user, get_users_count

DEFAULT_USERS = [
    {
        "username": "10000001",
        "password": "default123456",  # nosec B105
        "role": "normal",
        "nickname": "小杨",
        "must_change_password": True,  # nosec B105
        "status": "active",
    },
    {
        "username": "10000002",
        "password": "default123456",  # nosec B105
        "role": "admin",
        "nickname": "小李",
        "must_change_password": True,  # nosec B105
        "status": "active",
    },
    {
        "username": "10000003",
        "password": "default123456",  # nosec B105
        "role": "admin",
        "nickname": "小赵",
        "must_change_password": True,  # nosec B105
        "status": "no_active",
    },
]


def init_users():
    init_db()
    user_count = get_users_count()
    if user_count > 0:
        print(f"Users already exist: {user_count}. Skip default account initialization.")
        return

    for user in DEFAULT_USERS:
        create_user(**user)
        print(f"Created account: {user['username']} ({user['role']}, {user['status']})")

    print(f"Created {len(DEFAULT_USERS)} default accounts.")


if __name__ == "__main__":
    init_users()
