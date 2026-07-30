from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.infrastructure.persistence.session_repository import SessionRepository
from app.infrastructure.persistence.store import get_db, init_db
from test.app.interfaces.api._helpers import create_test_owner


def test_revoke_for_user_can_preserve_one_raw_cookie(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = create_test_owner(db_path)
    now = datetime.now(timezone.utc)
    with get_db(db_path) as connection:
        repository = SessionRepository(connection)
        current = repository.issue(owner_id, now + timedelta(hours=1))
        other = repository.issue(owner_id, now + timedelta(hours=1))
        connection.commit()

    # When
    with get_db(db_path) as connection:
        repository = SessionRepository(connection)
        repository.revoke_for_user(owner_id, now, except_raw_token=current)
        connection.commit()

    # Then
    with get_db(db_path) as connection:
        repository = SessionRepository(connection)
        assert repository.find_active(current, now) is not None
        assert repository.find_active(other, now) is None


def test_system_projection_excludes_expired_and_revoked_rows(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    owner_id = create_test_owner(db_path)
    now = datetime.now(timezone.utc)
    with get_db(db_path) as connection:
        repository = SessionRepository(connection)
        active = repository.issue(owner_id, now + timedelta(hours=1))
        revoked = repository.issue(owner_id, now + timedelta(hours=1))
        repository.issue(owner_id, now - timedelta(seconds=1))
        repository.revoke(revoked, now)
        connection.commit()

    # When
    with get_db(db_path) as connection:
        repository = SessionRepository(connection)
        count = repository.count_active(now)
        listed = repository.list_active(now, limit=20)

    # Then
    assert count == 1
    assert [record.username for record in listed] == ["owner"]
    assert listed[0].token_hash != active
