#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


PUBLIC_DEFAULTS = {
    "APP_SECRET": "case-library-demo-app-secret",
    "MINIO_ROOT_USER": "case-library-demo",
    "MINIO_ROOT_PASSWORD": "case-library-demo-secret",
    "BACKUP_AGE_RECIPIENT": "age1qwsucmt40ee3ajudtf5fs6p5a2t9vuqtwh6u4skrsdnz2ulsk9ls7ju9em",
    "BACKUP_AGE_IDENTITY": "AGE-SECRET-KEY-1RVN72Z4VX3UKTDQMKDGQWTQDPCG0K2837ZENLFCUJWAD75P9JL0QH6UJWS",
}


def secret(name: str) -> str:
    path = os.environ.get(f"{name}_FILE", "")
    try:
        return Path(path).read_text(encoding="utf-8").strip() if path else ""
    except OSError:
        return ""


def configured_values() -> dict[str, str]:
    values = {
        name: secret(name)
        for name in ("APP_SECRET", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD")
    }
    values["BACKUP_AGE_IDENTITY"] = secret("BACKUP_AGE_IDENTITY")
    values["BACKUP_AGE_RECIPIENT"] = os.environ.get("BACKUP_AGE_RECIPIENT", "").strip()
    return values


def diverse(value: str, minimum_bytes: int, minimum_unique: int) -> bool:
    encoded = value.encode("utf-8")
    return len(encoded) >= minimum_bytes and len(set(encoded)) >= minimum_unique


def age_recipient(identity: str) -> str | None:
    try:
        result = subprocess.run(
            ["age-keygen", "-y"],
            input=f"{identity}\n",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def unsafe_name(values: dict[str, str]) -> str | None:
    for name, value in values.items():
        if not value or value == PUBLIC_DEFAULTS[name]:
            return name
    if not diverse(values["APP_SECRET"], 32, 8):
        return "APP_SECRET"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,31}", values["MINIO_ROOT_USER"]):
        return "MINIO_ROOT_USER"
    if not diverse(values["MINIO_ROOT_PASSWORD"], 16, 8):
        return "MINIO_ROOT_PASSWORD"
    recipient = age_recipient(values["BACKUP_AGE_IDENTITY"])
    if not recipient:
        return "BACKUP_AGE_IDENTITY"
    if recipient != values["BACKUP_AGE_RECIPIENT"]:
        return "BACKUP_AGE_RECIPIENT"
    return None


def main() -> int:
    if os.environ.get("APP_ENV", "production").strip().lower() != "production":
        return 0
    name = unsafe_name(configured_values())
    if name:
        print(f"Unsafe production configuration: {name}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
