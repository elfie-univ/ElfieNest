"""Transaction and row-count contracts for member mutations."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
    MemberCapacityError,
)
from app.infrastructure.persistence.store import get_db, hash_password, init_db


def _create_member(
    db_path: str, account_id: str = "member01", role: str = "user"
) -> int:
    with get_db(db_path) as connection:
        row = connection.execute(
            """INSERT INTO users (account_id, password_hash, role)
               VALUES (?, ?, ?) RETURNING id""",
            (account_id, hash_password("member-secret"), role),
        ).fetchone()
        connection.commit()
    assert row is not None
    return int(row[0])


def test_create_member_accepts_admin_role(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    user_id = InterfaceQueryRepository(db_path).create_member(
        account_id="admin01",
        display_name="Admin",
        password_hash=hash_password("admin-secret"),
        role="admin",
    )

    assert user_id is not None
    row = InterfaceQueryRepository(db_path).get_user(user_id)
    assert row is not None
    assert row.role == "admin"


def test_create_member_reports_admin_capacity_error(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    _create_member(db_path, "owner01", "owner")
    repository = InterfaceQueryRepository(db_path)
    for index in range(1, 6):
        assert (
            repository.create_member(
                account_id=f"admin{index:02d}",
                display_name=None,
                password_hash=hash_password("admin-secret"),
                role="admin",
            )
            is not None
        )

    with pytest.raises(MemberCapacityError):
        repository.create_member(
            account_id="admin06",
            display_name=None,
            password_hash=hash_password("admin-secret"),
            role="admin",
        )


def test_update_member_limit_accepts_admin_and_user_but_not_owner(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = _create_member(db_path, "owner01", "owner")
    admin_id = _create_member(db_path, "admin01", "admin")
    user_id = _create_member(db_path, "user01", "user")
    repository = InterfaceQueryRepository(db_path)

    assert repository.update_member_limit(admin_id, 6) is True
    assert repository.update_member_limit(user_id, 7) is True
    assert repository.update_member_limit(owner_id, 8) is False

    with get_db(db_path) as connection:
        rows = connection.execute(
            "SELECT id, elfie_limit FROM users WHERE id IN (?, ?, ?) ORDER BY id",
            (owner_id, admin_id, user_id),
        ).fetchall()
    assert [(row["id"], row["elfie_limit"]) for row in rows] == [
        (owner_id, None),
        (admin_id, 6),
        (user_id, 7),
    ]


def test_delete_member_reports_guarded_noop_when_elfie_exists(tmp_path: Path) -> None:
    """Given an owned Elfie, deleting the member returns false and keeps the row."""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    user_id = _create_member(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            """INSERT INTO elfies
               (elfie_id, name, owner_user_id, species, adopted_at, status)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'offline')""",
            ("00000001", "Elfie", user_id, "fox"),
        )
        connection.commit()

    deleted = InterfaceQueryRepository(db_path).delete_member(user_id)

    assert deleted is False
    assert InterfaceQueryRepository(db_path).get_user(user_id) is not None


def test_delete_member_reports_success_after_guard_passes(tmp_path: Path) -> None:
    """Given a member without Elfies, deleting the member returns true."""
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    user_id = _create_member(db_path)

    deleted = InterfaceQueryRepository(db_path).delete_member(user_id)

    assert deleted is True
    assert InterfaceQueryRepository(db_path).get_user(user_id) is None
