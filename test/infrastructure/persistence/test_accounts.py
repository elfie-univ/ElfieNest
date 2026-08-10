from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.features.accounts import AccountPersistenceConflict
from infrastructure.persistence.store import get_db, hash_password, init_db
from infrastructure.persistence import (
    SessionRepository,
    SQLiteAccountsAdapter,
    hash_session_token,
)
from test.app.interfaces.api._helpers import create_test_owner


def test_session_repository_stores_only_hash_and_revokes_raw_token(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    now = datetime.now(timezone.utc)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                "INSERT INTO users (account_id,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        repository = SessionRepository(connection)
        raw_token = repository.issue(user_id, now + timedelta(hours=1))
        connection.commit()

    with get_db(db_path) as connection:
        stored = str(
            connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        )
        repository = SessionRepository(connection)
        principal = repository.find_active(raw_token, now)
        repository.revoke(raw_token, now)
        connection.commit()

    assert stored == hash_session_token(raw_token)
    assert raw_token != stored
    assert principal is not None
    assert principal.account_id == "owner"
    with get_db(db_path) as connection:
        assert SessionRepository(connection).find_active(raw_token, now) is None


def test_session_repository_rejects_expired_hash(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    now = datetime.now(timezone.utc)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                "INSERT INTO users (account_id,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        raw_token = SessionRepository(connection).issue(
            user_id, now - timedelta(seconds=1)
        )
        connection.commit()

    with get_db(db_path) as connection:
        assert SessionRepository(connection).find_active(raw_token, now) is None


def test_sqlite_accounts_adapter_round_trips_strict_principal(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    user_id = create_test_owner(db_path)
    adapter = SQLiteAccountsAdapter(db_path)
    now = datetime.now(timezone.utc)

    token = adapter.issue_session(user_id, now + timedelta(hours=1))
    principal = adapter.find_session(token, now)

    assert principal is not None
    assert principal.user_id == user_id
    assert principal.account_id == "owner"
    assert principal.role == "owner"

    adapter.revoke_session(token, now)
    assert adapter.find_session(token, now) is None


def test_first_owner_creation_is_atomic_and_idempotent(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteAccountsAdapter(db_path)

    created = adapter.create_first_owner(
        account_id="owner",
        display_name="Owner",
        password_hash=hash_password("secret123"),
    )
    repeated = adapter.create_first_owner(
        account_id="ignored",
        display_name=None,
        password_hash=hash_password("different123"),
    )

    assert repeated == created
    with get_db(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_first_owner_creation_rejects_a_non_owner_account_population(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (account_id,password_hash,role) VALUES (?,?,'user')",
            ("member", hash_password("secret123")),
        )
        connection.commit()

    with pytest.raises(AccountPersistenceConflict):
        SQLiteAccountsAdapter(db_path).create_first_owner(
            account_id="owner",
            display_name=None,
            password_hash=hash_password("secret123"),
        )
