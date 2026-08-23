from __future__ import annotations

from pathlib import Path

from bson.binary import Binary
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.Random import get_random_bytes

NONCE_BYTES = 12
TAG_BYTES = 16
KEY_CONTEXT = b"case-library:ai-user-api-key:v1"


class SecretCipherError(Exception):
    pass


def _root_secret(path: str) -> bytes:
    try:
        secret = Path(path).read_bytes().strip() if path else b""
    except OSError:
        secret = b""
    if not secret:
        raise SecretCipherError("应用密钥不可用")
    return secret


def _key(path: str) -> bytes:
    return HKDF(_root_secret(path), 32, b"", SHA256, context=KEY_CONTEXT)


def _aad(user_id: str) -> bytes:
    return KEY_CONTEXT + b":" + user_id.encode("utf-8")


def encrypt_api_key(api_key: str, user_id: str, secret_path: str) -> Binary:
    nonce = get_random_bytes(NONCE_BYTES)
    cipher = AES.new(_key(secret_path), AES.MODE_GCM, nonce=nonce)
    cipher.update(_aad(user_id))
    ciphertext, tag = cipher.encrypt_and_digest(api_key.encode("utf-8"))
    return Binary(nonce + tag + ciphertext)


def decrypt_api_key(value: bytes, user_id: str, secret_path: str) -> str:
    try:
        nonce, tag = value[:NONCE_BYTES], value[NONCE_BYTES : NONCE_BYTES + TAG_BYTES]
        ciphertext = value[NONCE_BYTES + TAG_BYTES :]
        cipher = AES.new(_key(secret_path), AES.MODE_GCM, nonce=nonce)
        cipher.update(_aad(user_id))
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except (ValueError, UnicodeError, SecretCipherError) as error:
        raise SecretCipherError("个人 AI 配置不可用") from error
