from __future__ import annotations

from pathlib import Path

import pytest

from elfienest.operations.setup_service import (
    SetupAlreadyCompleteError,
    create_first_admin,
    create_first_admin_account,
)
from elfienest.persistence.store import get_db, init_db


def test_create_first_admin_account_does_not_create_session(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    account = create_first_admin_account(
        db_path, username="admin", password="secret123"
    )

    with get_db(db_path) as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert account.username == "admin"
    assert account.role == "admin"
    assert session_count == 0


def test_create_first_admin_creates_login_session(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    setup_result = create_first_admin(db_path, username="admin", password="secret123")

    with get_db(db_path) as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert setup_result.session_token
    assert setup_result.csrf_token
    assert session_count == 1


def test_create_first_admin_account_rejects_existing_user(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_admin_account(db_path, username="admin", password="secret123")

    with pytest.raises(SetupAlreadyCompleteError):
        create_first_admin_account(db_path, username="other", password="secret123")
