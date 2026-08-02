"""Transaction and row-count contracts for member mutations."""

from __future__ import annotations

from pathlib import Path

from app.infrastructure.persistence.interface_query_repository import (
    InterfaceQueryRepository,
)
from app.infrastructure.persistence.store import get_db, hash_password, init_db


def _create_member(db_path: str) -> int:
    with get_db(db_path) as connection:
        row = connection.execute(
            """INSERT INTO users (account_id, password_hash, role)
               VALUES (?, ?, 'user') RETURNING id""",
            ("member01", hash_password("member-secret")),
        ).fetchone()
        connection.commit()
    assert row is not None
    return int(row[0])


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
