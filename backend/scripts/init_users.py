#!/usr/bin/env python3
"""Initialize default MongoDB accounts when the users collection is empty."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import create_user, get_users_count, init_db

DEFAULT_USERS = [
    {
        "username": "10000001",
        "password": "default123456",
        "role": "normal",
        "nickname": "小杨",
        "must_change_password": True,
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
    {
        "username": "10000003",
        "password": "default123456",
        "role": "admin",
        "nickname": "小赵",
        "must_change_password": True,
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
