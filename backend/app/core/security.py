#!/usr/bin/env python3
"""Authentication token helpers for the case library API."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from backend.repositories.users import get_user_by_username

AUTH_SECRET = os.getenv("AUTH_SECRET")
if not AUTH_SECRET:
    AUTH_SECRET = secrets.token_urlsafe(32)
    print(
        "WARNING: AUTH_SECRET is not set. A random secret was generated for this "
        "process; tokens will be invalidated on restart. Set AUTH_SECRET in production."
    )
_AUTH_SECRET_BYTES = AUTH_SECRET.encode("utf-8")
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL", str(7 * 24 * 3600)))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _normalize_token_version(value) -> int:
    try:
        version = int(value)
    except (TypeError, ValueError):
        return 0
    return max(version, 0)


def create_auth_token(username: str, token_version: int = 0) -> str:
    now = int(time.time())
    payload = {
        "u": username,
        "tv": _normalize_token_version(token_version),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_AUTH_SECRET_BYTES, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(sig)}"


def verify_auth_token(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected_sig = hmac.new(
            _AUTH_SECRET_BYTES, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    username = payload.get("u")
    if not isinstance(username, str) or not username:
        return None
    return {"username": username, "token_version": _normalize_token_version(payload.get("tv"))}


def get_current_user(headers):
    auth_header = headers.get("authorization") or headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token_payload = verify_auth_token(parts[1].strip())
    if not token_payload:
        return None
    user = get_user_by_username(token_payload["username"])
    if (
        user
        and user.get("status") == "active"
        and _normalize_token_version(user.get("token_version"))
        == token_payload["token_version"]
    ):
        return user
    return None


def get_case_owner_username(case: dict) -> str:
    return case.get("owner_username") or case.get("author") or ""
