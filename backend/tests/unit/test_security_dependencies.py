#!/usr/bin/env python3
"""Unit checks for auth tokens and route dependency helpers."""

# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

os.environ["AUTH_SECRET"] = "unit-test-auth-secret"
os.environ["MONGODB_DB_NAME"] = f"case_library_security_unit_{uuid4().hex[:8]}"

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException

from backend.app.core import dependencies, security


def test_create_and_verify_auth_token_normalizes_token_version():
    token = security.create_auth_token("alice", token_version="bad")
    assert security.verify_auth_token(token) == {"username": "alice", "token_version": 0}

    token = security.create_auth_token("alice", token_version=-9)
    assert security.verify_auth_token(token)["token_version"] == 0

    token = security.create_auth_token("alice", token_version=3)
    assert security.verify_auth_token(token) == {"username": "alice", "token_version": 3}


def test_verify_auth_token_rejects_tampered_and_expired_tokens():
    token = security.create_auth_token("alice", token_version=1)
    payload, sig = token.split(".", 1)
    tampered_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert security.verify_auth_token(f"{payload}.{tampered_sig}") is None

    old_ttl = security.TOKEN_TTL_SECONDS
    try:
        security.TOKEN_TTL_SECONDS = -1
        expired = security.create_auth_token("alice")
    finally:
        security.TOKEN_TTL_SECONDS = old_ttl
    assert security.verify_auth_token(expired) is None
    assert security.verify_auth_token("not-a-token") is None


def test_get_current_user_requires_active_user_and_matching_token_version():
    users = {
        "active": {"username": "active", "status": "active", "token_version": 2},
        "inactive": {"username": "inactive", "status": "inactive", "token_version": 0},
        "rotated": {"username": "rotated", "status": "active", "token_version": 3},
    }
    old_get_user = security.get_user_by_username
    try:
        security.get_user_by_username = lambda username: users.get(username)

        active_token = security.create_auth_token("active", token_version=2)
        assert security.get_current_user({"Authorization": f"Bearer {active_token}"}) == users["active"]

        inactive_token = security.create_auth_token("inactive")
        assert security.get_current_user({"Authorization": f"Bearer {inactive_token}"}) is None

        rotated_token = security.create_auth_token("rotated", token_version=2)
        assert security.get_current_user({"Authorization": f"Bearer {rotated_token}"}) is None

        assert security.get_current_user({}) is None
        assert security.get_current_user({"Authorization": active_token}) is None
    finally:
        security.get_user_by_username = old_get_user


def test_ensure_case_history_visible_allows_owner_and_admin_only():
    old_get_case = dependencies.get_case
    try:
        dependencies.get_case = lambda case_id, include_deleted=False: {
            "id": case_id,
            "owner_username": "owner",
            "author": "legacy-author",
        }

        owner = {"username": "owner", "role": "normal"}
        admin = {"username": "admin", "role": "admin"}
        stranger = {"username": "stranger", "role": "normal"}

        assert dependencies.ensure_case_history_visible(1, owner)["id"] == 1
        assert dependencies.ensure_case_history_visible(1, admin)["id"] == 1

        for user in (None, stranger):
            try:
                dependencies.ensure_case_history_visible(1, user)
            except HTTPException as exc:
                assert exc.status_code == 403
            else:
                raise AssertionError("non-owner history access should fail")

        dependencies.get_case = lambda case_id, include_deleted=False: None
        try:
            dependencies.ensure_case_history_visible(404, owner)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("missing case should fail")
    finally:
        dependencies.get_case = old_get_case


def main() -> None:
    test_create_and_verify_auth_token_normalizes_token_version()
    test_verify_auth_token_rejects_tampered_and_expired_tokens()
    test_get_current_user_requires_active_user_and_matching_token_version()
    test_ensure_case_history_visible_allows_owner_and_admin_only()
    print("security dependency unit checks passed")


if __name__ == "__main__":
    main()
