from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.infrastructure.persistence.session_repository import (
    SessionRepository,
    hash_session_token,
)
from app.infrastructure.persistence.store import get_db, hash_password, init_db


def test_session_repository_stores_only_hash_and_revokes_raw_token(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    now = datetime.now(timezone.utc)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                "INSERT INTO users (username,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        repository = SessionRepository(connection)
        raw_token = repository.issue(user_id, now + timedelta(hours=1))
        connection.commit()

    with get_db(db_path) as connection:
        stored = str(connection.execute("SELECT token_hash FROM sessions").fetchone()[0])
        repository = SessionRepository(connection)
        principal = repository.find_active(raw_token, now)
        repository.revoke(raw_token, now)
        connection.commit()

    assert stored == hash_session_token(raw_token)
    assert raw_token != stored
    assert principal is not None
    assert principal.username == "owner"
    with get_db(db_path) as connection:
        assert SessionRepository(connection).find_active(raw_token, now) is None


def test_session_repository_rejects_expired_hash(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    now = datetime.now(timezone.utc)
    with get_db(db_path) as connection:
        user_id = int(
            connection.execute(
                "INSERT INTO users (username,password_hash,role) VALUES (?,?,'owner')",
                ("owner", hash_password("secret123")),
            ).lastrowid
        )
        raw_token = SessionRepository(connection).issue(
            user_id, now - timedelta(seconds=1)
        )
        connection.commit()

    with get_db(db_path) as connection:
        assert SessionRepository(connection).find_active(raw_token, now) is None
