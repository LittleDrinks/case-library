from __future__ import annotations

import secrets


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(12)}"
