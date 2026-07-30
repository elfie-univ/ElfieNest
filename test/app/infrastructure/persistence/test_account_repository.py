from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.persistence.account_repository import (
    AccountConflictError,
    AccountRepository,
)
from app.infrastructure.persistence.store import get_db, hash_password, init_db


def test_final_account_projection_preserves_profile_fields(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        repository = AccountRepository(connection)
        user_id = repository.create_owner(
            username="owner",
            password_hash=hash_password("secret123"),
            nickname="Owner Name",
            avatar_color=7,
        )
        repository.update_avatar_path(user_id, "assets/users/1/avatar.png")
        repository.update_quota(user_id, 12)
        repository.update_theme(user_id, "harbor-blue")
        connection.commit()

    with get_db(db_path) as connection:
        account = AccountRepository(connection).find_owner()

    assert account is not None
    assert account.nickname == "Owner Name"
    assert account.avatar_color == 7
    assert account.avatar_kind == "initials"
    assert account.avatar_path == "assets/users/1/avatar.png"
    assert account.elfie_limit == 12
    assert account.theme_key == "harbor-blue"


def test_final_schema_rejects_second_owner(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        repository = AccountRepository(connection)
        repository.create_owner(
            username="owner-one",
            password_hash=hash_password("secret123"),
            nickname="One",
            avatar_color=0,
        )
        with pytest.raises(AccountConflictError):
            repository.create_owner(
                username="owner-two",
                password_hash=hash_password("secret456"),
                nickname="Two",
                avatar_color=1,
            )
