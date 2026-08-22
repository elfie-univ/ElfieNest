"""Cookie-bound CSRF protection owned by the HTTP interface."""

from __future__ import annotations

import hmac

_CSRF_CONTEXT = b"elfienest-csrf-v1"


def generate_csrf_token(session_token: str) -> str:
    """Derive a restart-stable token from the high-entropy session secret."""
    return hmac.new(
        session_token.encode("utf-8"),
        _CSRF_CONTEXT,
        "sha256",
    ).hexdigest()


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    if not session_token or not csrf_token:
        return False
    return hmac.compare_digest(generate_csrf_token(session_token), csrf_token)


__all__ = ("generate_csrf_token", "verify_csrf_token")
