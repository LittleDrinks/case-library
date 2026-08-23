from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path

from app.modules.cases.service import CaseError

KEY_CONTEXT = b"case-library:search-cursor:v1"


@dataclass(frozen=True, slots=True)
class CursorState:
    page: int
    offset: int


def principal_key(user: dict | None) -> str:
    return "anonymous" if not user else f"{user['role']}:{user['id']}"


def _scope_filters(filters: dict) -> dict:
    return {
        name: sorted(value) if isinstance(value, (list, tuple)) else value
        for name, value in filters.items()
    }


def scope_key(
    query: str, kind: str, page_size: int, filters: dict, user, generation: str
) -> str:
    payload = [
        _normalize_query(query),
        kind,
        page_size,
        _scope_filters(filters),
        principal_key(user),
        generation,
    ]
    raw = _json(payload)
    return hashlib.sha256(raw).hexdigest()


def decode_cursor(token: str | None, scope: str, secret_path: str) -> CursorState:
    key = _key(secret_path)
    if not token:
        return CursorState(1, 0)
    payload = _signed_payload(token, key)
    if payload.get("scope") != scope or not _valid_payload(payload):
        raise CaseError(422, "分页游标无效")
    return CursorState(payload["page"], payload["offset"])


def _normalize_query(query: str) -> str:
    return " ".join(query.split())


def encode_cursor(page: int, offset: int, scope: str, secret_path: str) -> str:
    payload = {"v": 2, "page": page, "offset": offset, "scope": scope}
    raw = _json(payload)
    body = _encode(raw)
    signature = hmac.digest(_key(secret_path), body.encode(), "sha256")
    return f"{body}.{_encode(signature)}"


def _key(path: str) -> bytes:
    try:
        secret = Path(path).read_bytes().strip() if path else b""
    except OSError:
        secret = b""
    if not secret:
        raise CaseError(503, "分页服务不可用")
    return hmac.digest(secret, KEY_CONTEXT, "sha256")


def _signed_payload(token: str, key: bytes) -> dict:
    try:
        body, encoded_signature = token.split(".")
        signature = _decode(encoded_signature)
        expected = hmac.digest(key, body.encode(), "sha256")
    except (ValueError, UnicodeError):
        raise CaseError(422, "分页游标无效") from None
    if not hmac.compare_digest(signature, expected):
        raise CaseError(422, "分页游标无效")
    return _payload(_decode(body))


def _payload(raw: bytes) -> dict:
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CaseError(422, "分页游标无效") from error
    if not isinstance(payload, dict):
        raise CaseError(422, "分页游标无效")
    return payload


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    raw = base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
    )
    if _encode(raw) != value:
        raise ValueError("non-canonical base64")
    return raw


def _json(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()


def _valid_payload(payload: dict) -> bool:
    return (
        payload.get("v") == 2
        and isinstance(payload.get("page"), int)
        and 1 <= payload["page"] <= 1_000_000
        and isinstance(payload.get("offset"), int)
        and 0 <= payload["offset"] <= 10_000_000
    )
