"""Accounts-owned password hashing policy."""

from __future__ import annotations

import hashlib
import secrets

_PASSWORD_HASH_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PASSWORD_HASH_ITERATIONS,
    )
    return f"pbkdf2_sha256${_PASSWORD_HASH_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    parts = hashed.split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        parts[2].encode("utf-8"),
        iterations,
    )
    return secrets.compare_digest(digest.hex(), parts[3])


__all__ = ("hash_password", "verify_password")
