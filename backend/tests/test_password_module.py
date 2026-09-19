"""密码模块默认成本与验证合同：不经过 client fixture，无任何 patch。"""
from __future__ import annotations

from app.modules.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    hash_password,
    require_strong_password,
    verify_password,
)


def test_hash_uses_production_default_cost_and_roundtrip() -> None:
    encoded = hash_password("correct horse battery staple")
    # 生产默认 12 轮：成本因子编码在哈希前缀中，防止默认参数被静默调低
    assert encoded.startswith("$2b$12$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_verify_rejects_garbage_hash_without_raising() -> None:
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_password_policy_enforces_minimum_length() -> None:
    try:
        require_strong_password("x" * (MIN_PASSWORD_LENGTH - 1))
    except PasswordPolicyError:
        pass
    else:
        raise AssertionError("short password must be rejected")
