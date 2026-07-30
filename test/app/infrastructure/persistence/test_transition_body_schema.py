"""Card 9 transition schema tests for external bodies and lease v2 rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.store import get_db, init_db
from app.infrastructure.persistence.transition_body_schema import (
    TransitionLeaseConflict,
    ensure_body_transition_schema,
    start_embodiment_lease_v2,
    update_embodiment_lease_v2,
)
from app.infrastructure.persistence.transition_elfie_nest_schema import (
    ensure_elfie_nest_transition_schema,
)

VALID_HASH = "a" * 64


def test_body_transition_schema_preserves_old_audit_table_and_adds_v2_tables(
    tmp_path: Path,
) -> None:
    # Given: normal initialization already has the legacy device audit table.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        assert "device_id" in _columns(connection, "device_audit_events")
        assert "detail" in _columns(connection, "device_audit_events")
        assert _table_exists(connection, "external_bodies") is False

        # When: Card 9 transition DDL is explicitly applied.
        ensure_body_transition_schema(connection)

        # Then: old runtime tables remain and final fields use clear v2 names.
        assert "device_id" in _columns(connection, "device_audit_events")
        assert "body_id" not in _columns(connection, "device_audit_events")
        assert {
            "body_id",
            "owner_elfie_id",
            "body_type",
            "secret_hash",
            "status",
        }.issubset(_columns(connection, "external_bodies"))
        assert _is_not_null(connection, "external_bodies", "body_id") is True
        assert {"body_id", "event_type", "detail_json"}.issubset(
            _columns(connection, "device_audit_events_v2")
        )
        assert "lease_version" in _columns(connection, "embodiment_sessions_v2")
        assert "session_id" not in _columns(connection, "embodiment_sessions_v2")
        assert _is_not_null(connection, "embodiment_sessions_v2", "elfie_id") is True
        assert (
            _column_type(connection, "embodiment_sessions_v2", "lease_expires_at")
            == "TEXT"
        )


def test_body_transition_rejects_revoked_body_and_stale_lease_writes(
    tmp_path: Path,
) -> None:
    # Given: one final Elfie and one active external body in a temporary DB.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        ensure_elfie_nest_transition_schema(connection)
        ensure_body_transition_schema(connection)
        owner_id = connection.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES ('owner', 'hash', 'owner')
            """
        ).lastrowid
        connection.execute(
            """
            INSERT INTO elfies
                (elfie_id, name, owner_user_id, species, adopted_at, status)
            VALUES ('00000001', '小狐', ?, 'fox', '2026-07-29T00:00:00Z', 'online')
            """,
            (owner_id,),
        )
        connection.execute(
            """
            INSERT INTO elfies
                (elfie_id, name, owner_user_id, species, adopted_at, status)
            VALUES ('00000002', '小鹿', ?, 'deer', '2026-07-29T00:00:00Z', 'online')
            """,
            (owner_id,),
        )
        _insert_body(connection, "body-1", "00000001", "active")
        _insert_body(connection, "body-2", "00000002", "active")
        _insert_body(
            connection,
            "body-revoked",
            "00000001",
            "revoked",
            "2026-07-29T00:10:00Z",
        )

        # When: a lease is started and then advanced with the expected version.
        expires_at = "2026-07-29T00:15:00Z"
        first = start_embodiment_lease_v2(
            connection,
            elfie_id="00000001",
            body_id="body-1",
            state="hosted",
            lease_expires_at=expires_at,
        )
        second = update_embodiment_lease_v2(
            connection,
            elfie_id="00000001",
            expected_lease_version=first.lease_version,
            body_id="body-1",
            state="returning_to_nest",
            lease_expires_at="2026-07-29T00:16:00Z",
        )

        # Then: version checks and revoked-body checks are durable write gates.
        assert first.lease_expires_at == expires_at
        assert second.lease_version == first.lease_version + 1
        with pytest.raises(TransitionLeaseConflict):
            start_embodiment_lease_v2(
                connection,
                elfie_id="00000001",
                body_id="body-2",
                state="hosted",
                lease_expires_at="2026-07-29T00:17:00Z",
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO embodiment_sessions_v2
                    (elfie_id, body_id, state, lease_expires_at, lease_version)
                VALUES ('00000002', 'body-1', 'hosted', '2026-07-29T00:17:00Z', 1)
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE external_bodies
                SET owner_elfie_id = '00000002'
                WHERE body_id = 'body-1'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE external_bodies
                SET status = 'revoked'
                WHERE body_id = 'body-1'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE external_bodies
                SET revoked_at = '2026-07-29T00:18:00Z'
                WHERE body_id = 'body-1'
                """
            )
        with pytest.raises(TransitionLeaseConflict):
            update_embodiment_lease_v2(
                connection,
                elfie_id="00000001",
                expected_lease_version=first.lease_version,
                body_id="body-1",
                state="hosted",
                lease_expires_at="2026-07-29T00:17:00Z",
            )
        with pytest.raises(TransitionLeaseConflict):
            update_embodiment_lease_v2(
                connection,
                elfie_id="00000001",
                expected_lease_version=second.lease_version,
                body_id="body-revoked",
                state="hosted",
                lease_expires_at="2026-07-29T00:17:00Z",
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO device_audit_events_v2
                    (body_id, event_type, detail_json)
                VALUES ('body-1', 'heartbeat', 'not-json')
                """
            )
        for invalid_json in ("[]", '"scalar"', "null"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO device_audit_events_v2
                        (body_id, event_type, detail_json)
                    VALUES ('body-1', 'heartbeat', ?)
                    """,
                    (invalid_json,),
                )

        connection.execute(
            """
            UPDATE embodiment_sessions_v2
            SET body_id = NULL,
                state = 'at_nest',
                lease_expires_at = NULL,
                lease_version = lease_version + 1
            WHERE elfie_id = '00000001'
            """
        )
        connection.execute(
            """
            UPDATE external_bodies
            SET status = 'revoked',
                revoked_at = '2026-07-29T00:19:00Z'
            WHERE body_id = 'body-1'
            """
        )
        row = connection.execute(
            "SELECT status, revoked_at FROM external_bodies WHERE body_id = 'body-1'"
        ).fetchone()
        assert row["status"] == "revoked"
        assert row["revoked_at"] == "2026-07-29T00:19:00Z"


def _insert_body(
    connection: sqlite3.Connection,
    body_id: str,
    owner_elfie_id: str,
    status: str,
    revoked_at: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO external_bodies
            (body_id, owner_elfie_id, display_name, body_type,
             secret_hash, status, revoked_at)
        VALUES (?, ?, 'Toy Body', 'toy', ?, ?, ?)
        """,
        (body_id, owner_elfie_id, VALID_HASH, status, revoked_at),
    )


def _columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _is_not_null(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(
        str(row["name"]) == column_name and int(row["notnull"]) == 1
        for row in rows
    )


def _column_type(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> str:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    for row in rows:
        if str(row["name"]) == column_name:
            return str(row["type"])
    raise AssertionError(f"missing column {table_name}.{column_name}")
