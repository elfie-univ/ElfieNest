from __future__ import annotations

import pytest

from app.features.accounts.roles import (
    AccountRoleError,
    can_manage_role,
    is_manager,
    parse_account_role,
    role_rank,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    (("owner", "owner"), ("admin", "admin"), ("user", "user")),
)
def test_parse_account_role_accepts_canonical_values(raw: str, expected: str) -> None:
    assert parse_account_role(raw) == expected


def test_parse_account_role_rejects_unknown_values() -> None:
    with pytest.raises(AccountRoleError):
        parse_account_role("manager")


@pytest.mark.parametrize(
    ("actor", "target", "expected"),
    (
        ("owner", "admin", True),
        ("owner", "user", True),
        ("admin", "user", True),
        ("admin", "admin", False),
        ("admin", "owner", False),
        ("user", "user", False),
    ),
)
def test_can_manage_role_requires_a_strictly_lower_target(
    actor: str, target: str, expected: bool
) -> None:
    assert can_manage_role(actor, target) is expected


def test_role_rank_and_manager_predicate() -> None:
    assert role_rank("owner") > role_rank("admin") > role_rank("user")
    assert is_manager("owner") is True
    assert is_manager("admin") is True
    assert is_manager("user") is False
