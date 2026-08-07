"""Contract tests for the inactive final ``nest.db`` builder."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path
from typing import Final

import pytest

from app.infrastructure.persistence.final_schema import (
    FinalNestDatabasePathError,
    create_final_nest_database,
)
from app.infrastructure.persistence.sqlite_connection import app_sqlite_connection

EXPECTED_TABLES: Final = {
    "users",
    "sessions",
    "local_installations",
    "elfies",
    "nest_settings",
    "external_bodies",
    "device_audit_events",
    "embodiment_sessions",
    "food_packages",
}
EXPECTED_COLUMNS: Final = {
    "users": {
        "id",
        "account_id",
        "display_name",
        "avatar_color",
        "avatar_kind",
        "avatar_path",
        "gender",
        "birth_date",
        "role",
        "password_hash",
        "presence",
        "last_seen_at",
        "elfie_limit",
        "default_landing_page",
        "theme_key",
        "language",
        "created_at",
        "updated_at",
    },
    "sessions": {"token_hash", "user_id", "expires_at", "created_at", "revoked_at"},
    "local_installations": {
        "installation_id",
        "owner_user_id",
        "device_name",
        "platform",
        "machine_id_hash",
        "setup_state",
        "setup_step",
        "owner_completed_at",
        "providers_completed_at",
        "nest_completed_at",
        "food_completed_at",
        "completed_at",
        "last_seen_at",
        "active_task_step",
        "active_task_key",
        "task_state",
        "task_progress",
        "last_error",
        "setup_draft_json",
        "created_at",
        "updated_at",
    },
    "nest_settings": {
        "nest_id",
        "bed_count",
        "tick_interval_sec",
        "max_elfies",
        "applied_world_revision",
        "clock_anchor_seconds",
        "created_at",
        "updated_at",
    },
    "elfies": {
        "elfie_id",
        "name",
        "owner_user_id",
        "species",
        "gender",
        "birth_date",
        "adopted_at",
        "bed_number",
        "status",
        "summary",
        "main_food_id",
        "created_at",
        "updated_at",
    },
    "external_bodies": {
        "body_id",
        "owner_elfie_id",
        "display_name",
        "body_type",
        "secret_hash",
        "status",
        "last_heartbeat_at",
        "created_at",
        "updated_at",
        "revoked_at",
    },
    "device_audit_events": {"id", "body_id", "event_type", "detail_json", "created_at"},
    "embodiment_sessions": {
        "elfie_id",
        "body_id",
        "state",
        "lease_expires_at",
        "lease_version",
        "updated_at",
    },
    "food_packages": {
        "food_key",
        "display_name",
        "system_role",
        "primary_model_ref",
        "reasoning_model_ref",
        "vision_model_ref",
        "tool_model_ref",
        "fallback_model_ref",
        "visibility_mode",
        "visible_user_ids_json",
        "enabled",
        "archived",
        "created_at",
        "updated_at",
    },
}
VALID_HASH: Final = "a" * 64


def test_final_nest_builder_creates_exact_schema_idempotently(tmp_path: Path) -> None:
    # Given: an explicit empty final database path.
    db_path = tmp_path / "nest.db"

    # When: the final builder runs twice.
    assert create_final_nest_database(db_path) == db_path
    assert create_final_nest_database(db_path) == db_path

    # Then: only the contract-approved tables and every approved column exist.
    with app_sqlite_connection(db_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables == EXPECTED_TABLES
        for table_name, expected in EXPECTED_COLUMNS.items():
            assert _columns(connection, table_name) == expected
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_final_nest_builder_rejects_wrong_name_and_symlink(tmp_path: Path) -> None:
    # Given: a wrong target name and a symlink named like the final database.
    target = tmp_path / "target.db"
    target.touch()
    symlink = tmp_path / "nest.db"
    symlink.symlink_to(target)

    # When/Then: neither a non-final name nor a symlink can be opened.
    with pytest.raises(FinalNestDatabasePathError):
        create_final_nest_database(tmp_path / "legacy.db")
    with pytest.raises(FinalNestDatabasePathError):
        create_final_nest_database(symlink)
    symlink.unlink()
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(FinalNestDatabasePathError):
        create_final_nest_database(linked_parent / "nest.db")


def test_final_account_constraints_reject_unsafe_direct_sql(tmp_path: Path) -> None:
    # Given: the final schema with its one owner.
    db_path = create_final_nest_database(tmp_path / "nest.db")
    with app_sqlite_connection(db_path) as connection:
        owner_id = _insert_user(connection, "owner", "owner")

        # When/Then: owner uniqueness, hashes, FKs and unsafe paths fail.
        with pytest.raises(sqlite3.IntegrityError):
            _insert_user(connection, "second-owner", "owner")
        for token_hash in ("raw-token", "A" * 64):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                    (token_hash, owner_id, "2099-01-01T00:00:00Z"),
                )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
                (VALID_HASH, 404, "2099-01-01T00:00:00Z"),
            )
        for avatar_path in (
            "/tmp/avatar.png",
            "../avatar.png",
            "safe/../avatar.png",
            "C:/avatar.png",
            "https://example.invalid/avatar.png",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE users SET avatar_path = ? WHERE id = ?",
                    (avatar_path, owner_id),
                )
        connection.execute(
            "INSERT INTO nest_settings(nest_id,bed_count,tick_interval_sec) VALUES('local',4,0.5)"
        )
        _insert_elfie(connection, owner_id)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO food_packages(food_key,display_name,visibility_mode,visible_user_ids_json) "
                "VALUES('invalid-json','Invalid','global','not-json')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE elfies SET main_food_id='' WHERE elfie_id='00000001'"
            )


def test_final_body_constraints_enforce_owner_json_and_revocation(
    tmp_path: Path,
) -> None:
    # Given: two Elfies, one active body, and one active lease.
    db_path = create_final_nest_database(tmp_path / "nest.db")
    with app_sqlite_connection(db_path) as connection:
        owner_id = _insert_user(connection, "owner", "owner")
        connection.execute(
            "INSERT INTO nest_settings(nest_id,bed_count,tick_interval_sec) VALUES('local',4,0.5)"
        )
        _insert_elfie(connection, owner_id, elfie_id="00000001")
        _insert_elfie(connection, owner_id, elfie_id="00000002")
        connection.execute(
            "INSERT INTO external_bodies(body_id,owner_elfie_id,display_name,body_type,secret_hash,status) "
            "VALUES('body-1','00000001','Toy','toy',?,'active')",
            (VALID_HASH,),
        )

        # When/Then: cross-owner leases and non-object audit JSON are rejected.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO embodiment_sessions(elfie_id,body_id,state,lease_version) "
                "VALUES('00000002','body-1','hosted',1)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO device_audit_events(body_id,event_type,detail_json) "
                "VALUES('body-1','heartbeat','[]')"
            )
        connection.execute(
            "INSERT INTO embodiment_sessions(elfie_id,body_id,state,lease_version) "
            "VALUES('00000001','body-1','hosted',1)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE external_bodies SET status='revoked',revoked_at=? WHERE body_id='body-1'",
                ("2026-07-30T00:00:00Z",),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE embodiment_sessions SET lease_version=3 WHERE elfie_id='00000001'"
            )

        # When: a stale conditional lease update is attempted.
        cursor = connection.execute(
            "UPDATE embodiment_sessions SET lease_version=lease_version+1 "
            "WHERE elfie_id='00000001' AND lease_version=0"
        )

        # Then: no durable row is changed.
        assert cursor.rowcount == 0
        assert (
            connection.execute(
                "SELECT lease_version FROM embodiment_sessions WHERE elfie_id='00000001'"
            ).fetchone()[0]
            == 1
        )


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _insert_user(connection: sqlite3.Connection, account_id: str, role: str) -> int:
    cursor = connection.execute(
        "INSERT INTO users(account_id,password_hash,role) VALUES(?,?,?)",
        (account_id, "password-hash", role),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _insert_elfie(
    connection: sqlite3.Connection,
    owner_id: int,
    *,
    elfie_id: str = "00000001",
) -> None:
    connection.execute(
        "INSERT INTO elfies(elfie_id,name,owner_user_id,species,adopted_at,status) "
        "VALUES(?, 'Elfie', ?, 'fox', '2026-07-30T00:00:00Z', 'offline')",
        (elfie_id, owner_id),
    )
