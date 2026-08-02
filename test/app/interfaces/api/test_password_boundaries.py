"""Regression tests for password strength at every HTTP request boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.interfaces.api.account_auth_routes import PasswordChange
from app.interfaces.api.owner_user_routes import CreateUserRequest
from app.interfaces.api.setup_models import SetupRequest


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            CreateUserRequest,
            {"account_id": "member01", "password": " 1234 ", "role": "user"},
        ),
        (SetupRequest, {"account_id": "owner", "password": " 1234 "}),
        (
            PasswordChange,
            {"old_password": "owner-secret", "new_password": " 1234 "},
        ),
    ],
)
def test_password_models_reject_short_values_after_trimming(
    model: type[CreateUserRequest] | type[SetupRequest] | type[PasswordChange],
    payload: dict[str, str],
) -> None:
    """Given a padded four-character secret, each boundary rejects it."""
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.parametrize("model", [SetupRequest, PasswordChange])
def test_password_models_reject_whitespace_only_values(
    model: type[SetupRequest] | type[PasswordChange],
) -> None:
    """Given a whitespace-only secret, the boundary rejects it."""
    payload = (
        {"account_id": "owner", "password": "      "}
        if model is SetupRequest
        else {"old_password": "owner-secret", "new_password": "      "}
    )
    with pytest.raises(ValidationError):
        model(**payload)
