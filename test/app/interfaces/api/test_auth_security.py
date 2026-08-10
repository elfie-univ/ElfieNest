"""HTTP CSRF token boundary tests."""

from app.interfaces.api.v1.auth import (
    generate_csrf_token,
    verify_csrf_token,
)


def test_csrf_token_is_bound_to_session() -> None:
    csrf = generate_csrf_token("session-a")
    assert verify_csrf_token("session-a", csrf) is True
    assert verify_csrf_token("session-b", csrf) is False
    assert verify_csrf_token("session-a", "") is False
