from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.features.accounts import (
    AccountPersistenceConflict,
    AccountProfileWrite,
    hash_password,
    verify_password,
)
from infrastructure.persistence.accounts import SQLiteAccountsAdapter
from infrastructure.persistence.nest_db.store import get_db, init_db


def _seed_accounts(db_path: str) -> tuple[int, int]:
    with get_db(db_path) as connection:
        owner_id = connection.execute(
            "INSERT INTO users (account_id,password_hash,role,display_name) "
            "VALUES (?,?, 'owner', ?)",
            ("owner", hash_password("owner-password"), "Owner"),
        ).lastrowid
        member_id = connection.execute(
            "INSERT INTO users (account_id,password_hash,role) VALUES (?,?, 'user')",
            ("member", hash_password("member-password")),
        ).lastrowid
        connection.commit()
    assert owner_id is not None
    assert member_id is not None
    return int(owner_id), int(member_id)


def test_profile_member_and_quota_operations_use_one_sqlite_adapter(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    owner_id, member_id = _seed_accounts(db_path)
    adapter = SQLiteAccountsAdapter(db_path)

    profile = adapter.update_profile(
        owner_id,
        AccountProfileWrite(
            account_id="owner-new",
            display_name="Owner New",
            gender="female",
            birth_date="1990-02-03",
            avatar_color=2,
            avatar_kind="emoji",
        ),
    )
    updated = adapter.update_managed_quota(member_id, 6)
    users = adapter.list_managed_accounts().items

    assert profile is not None
    assert profile.account_id == "owner-new"
    assert profile.gender == "female"
    assert updated is True
    assert (
        next(user for user in users if user.user_id == member_id).elfie_quota_override
        == 6
    )


def test_heartbeat_updates_presence_and_timestamp_atomically(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    owner_id, _ = _seed_accounts(db_path)
    adapter = SQLiteAccountsAdapter(db_path)
    timestamp = "2026-08-11T08:00:00.000000+00:00"

    assert adapter.record_heartbeat(owner_id, timestamp) is True

    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT presence,last_seen_at FROM users WHERE id=?", (owner_id,)
        ).fetchone()
    assert tuple(row) == ("online", timestamp)


def test_password_change_and_owner_recovery_revoke_the_expected_sessions(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    owner_id, member_id = _seed_accounts(db_path)
    adapter = SQLiteAccountsAdapter(db_path)
    current_token = adapter.issue_session(owner_id, _future())
    _ = adapter.issue_session(owner_id, _future())
    _ = adapter.issue_session(member_id, _future())

    adapter.change_password(owner_id, hash_password("changed-password"), current_token)
    recovered = adapter.recover_owner_account(
        owner_id, "owner-recovered", hash_password("recovered-password")
    )

    assert recovered is not None
    assert recovered.account_id == "owner-recovered"
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id=?", (owner_id,)
        ).fetchone()
        owner_active = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked_at IS NULL",
            (owner_id,),
        ).fetchone()[0]
        member_active = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked_at IS NULL",
            (member_id,),
        ).fetchone()[0]
    assert verify_password("recovered-password", str(row["password_hash"]))
    assert owner_active == 0
    assert member_active == 1


def test_owner_recovery_conflict_is_atomic(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    owner_id, _ = _seed_accounts(db_path)
    adapter = SQLiteAccountsAdapter(db_path)

    with pytest.raises(AccountPersistenceConflict):
        adapter.recover_owner_account(
            owner_id, "member", hash_password("recovered-password")
        )

    owner = adapter.find_owner_account()
    assert owner is not None
    assert owner.account_id == "owner"


def test_failed_member_delete_keeps_existing_sessions_atomic(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    _, member_id = _seed_accounts(db_path)
    adapter = SQLiteAccountsAdapter(db_path)
    _ = adapter.issue_session(member_id, _future())
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO elfies "
            "(elfie_id,name,owner_user_id,species,adopted_at,status) "
            "VALUES ('00000001','Elfie',?,'fox',CURRENT_TIMESTAMP,'offline')",
            (member_id,),
        )
        connection.commit()

    deleted = adapter.delete_managed_account(member_id)

    with get_db(db_path) as connection:
        active_sessions = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id=? AND revoked_at IS NULL",
            (member_id,),
        ).fetchone()[0]
    assert deleted is False
    assert active_sessions == 1


def test_avatar_storage_never_exposes_an_untrusted_path(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    owner_id, _ = _seed_accounts(db_path)
    adapter = SQLiteAccountsAdapter(db_path)
    content = b"\x89PNG\r\n\x1a\ncontent"

    stored = adapter.store(owner_id, "image/png", content)
    loaded = adapter.load(owner_id, "../../other/avatar.png")

    assert stored.relative_path == f"assets/users/{owner_id}/avatar.png"
    assert loaded is not None
    assert loaded.content == content


def _future() -> datetime:
    return datetime(2099, 1, 1, tzinfo=timezone.utc)
