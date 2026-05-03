#!/usr/bin/env python3
"""Initialize default users in MongoDB."""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from database import create_user, get_users_count, init_db


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def init_users():
    init_db()

    user_count = get_users_count()
    if user_count > 0:
        print(f"Users already exist: {user_count}. Skip default user initialization.")
        return

    users = [
        ("admin", "admin123", "admin"),
        ("user", "user123", "user"),
        ("test", "test123", "user"),
    ]

    created = 0
    for username, password, role in users:
        create_user(username, hash_password(password), role)
        created += 1
        print(f"Created user: {username} ({role})")

    print(f"Created {created} default users.")


if __name__ == "__main__":
    init_users()
