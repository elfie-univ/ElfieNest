from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).parents[4]
_ACCOUNT_CALLERS = (
    "app/interfaces/api/app.py",
    "app/interfaces/api/owner_user_routes.py",
    "app/interfaces/api/profile_routes.py",
    "app/features/administration/owner_service.py",
    "app/features/setup/service.py",
)
_DIRECT_USERS_SQL = re.compile(
    r"\b(?:FROM|INTO|UPDATE|DELETE\s+FROM)\s+users\b",
    flags=re.IGNORECASE,
)


@pytest.mark.parametrize("relative_path", _ACCOUNT_CALLERS)
def test_account_callers_delegate_legacy_users_sql(relative_path: str) -> None:
    # Given
    caller = _REPOSITORY_ROOT / relative_path

    # When
    source = caller.read_text(encoding="utf-8")

    # Then
    assert _DIRECT_USERS_SQL.search(source) is None
