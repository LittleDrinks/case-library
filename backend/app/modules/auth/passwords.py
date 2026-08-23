from __future__ import annotations

import bcrypt

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class PasswordPolicyError(ValueError):
    pass


def require_strong_password(password: str, label: str = "密码") -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"{label}至少 {MIN_PASSWORD_LENGTH} 个字符")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"{label}不能超过 {MAX_PASSWORD_LENGTH} 个字符")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), encoded.encode())
    except (ValueError, TypeError):
        return False
