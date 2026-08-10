"""Cookie-bound CSRF protection owned by the HTTP interface."""

from __future__ import annotations

import hmac
import secrets

_CSRF_SECRET = secrets.token_hex(32)


def generate_csrf_token(session_token: str) -> str:
    return hmac.new(
        _CSRF_SECRET.encode("utf-8"),
        session_token.encode("utf-8"),
        "sha256",
    ).hexdigest()


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    if not session_token or not csrf_token:
        return False
    return hmac.compare_digest(generate_csrf_token(session_token), csrf_token)


__all__ = ("generate_csrf_token", "verify_csrf_token")
