"""Regression tests for password strength at every HTTP request boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.interfaces.api.v1.admin.users.models import CreateManagedUserRequest
from app.interfaces.api.v1.me.models import PasswordChangeRequest
from app.interfaces.api.v1.setup.models import SetupOwnerDraftRequest


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            CreateManagedUserRequest,
            {"account_id": "member01", "password": " 1234 ", "role": "user"},
        ),
        (
            SetupOwnerDraftRequest,
            {
                "account_id": "owner",
                "password": " 1234 ",
                "confirm_password": " 1234 ",
            },
        ),
        (
            PasswordChangeRequest,
            {"old_password": "owner-secret", "new_password": " 1234 "},
        ),
    ],
)
def test_password_models_reject_short_values_after_trimming(
    model: type[CreateManagedUserRequest]
    | type[SetupOwnerDraftRequest]
    | type[PasswordChangeRequest],
    payload: dict[str, str],
) -> None:
    """Given a padded four-character secret, each boundary rejects it."""
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.parametrize("model", [SetupOwnerDraftRequest, PasswordChangeRequest])
def test_password_models_reject_whitespace_only_values(
    model: type[SetupOwnerDraftRequest] | type[PasswordChangeRequest],
) -> None:
    """Given a whitespace-only secret, the boundary rejects it."""
    payload = (
        {
            "account_id": "owner",
            "password": "      ",
            "confirm_password": "      ",
        }
        if model is SetupOwnerDraftRequest
        else {"old_password": "owner-secret", "new_password": "      "}
    )
    with pytest.raises(ValidationError):
        model(**payload)
