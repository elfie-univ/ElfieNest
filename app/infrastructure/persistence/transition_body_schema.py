"""Explicit transition DDL and lease helpers for Card 9 body storage."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class TransitionLeaseConflict(RuntimeError):
    """Raised when a Card 9 lease write is stale or targets a revoked body."""


@dataclass(frozen=True)
class TransitionLeaseRow:
    __slots__ = (
        "elfie_id",
        "body_id",
        "state",
        "lease_expires_at",
        "lease_version",
    )

    elfie_id: str
    body_id: str | None
    state: str
    lease_expires_at: str | None
    lease_version: int


def ensure_body_transition_schema(connection: sqlite3.Connection) -> None:
    """Create Card 9 transition tables while preserving legacy runtime tables."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS external_bodies (
            body_id TEXT NOT NULL PRIMARY KEY,
            owner_elfie_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            body_type TEXT NOT NULL CHECK(length(body_type) > 0),
            secret_hash TEXT NOT NULL
                CHECK(length(secret_hash) = 64
                    AND secret_hash NOT GLOB '*[^0-9a-f]*'),
            status TEXT NOT NULL CHECK(status IN ('available', 'active', 'revoked')),
            last_heartbeat_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at TEXT,
            CHECK(
                (status = 'revoked' AND revoked_at IS NOT NULL)
                OR (status <> 'revoked' AND revoked_at IS NULL)
            ),
            FOREIGN KEY(owner_elfie_id) REFERENCES elfies(elfie_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS device_audit_events_v2 (
            id INTEGER PRIMARY KEY,
            body_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}'
                CHECK(json_valid(detail_json) AND json_type(detail_json) = 'object'),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(body_id) REFERENCES external_bodies(body_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embodiment_sessions_v2 (
            elfie_id TEXT NOT NULL PRIMARY KEY,
            body_id TEXT,
            state TEXT NOT NULL CHECK(state IN (
                'at_nest', 'switching_to_hosted', 'hosted',
                'returning_to_nest', 'offline'
            )),
            lease_expires_at TEXT,
            lease_version INTEGER NOT NULL CHECK(lease_version >= 1),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(elfie_id) REFERENCES elfies(elfie_id),
            FOREIGN KEY(body_id) REFERENCES external_bodies(body_id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_device_audit_events_v2_body
        ON device_audit_events_v2(body_id)
        """
    )
    _ensure_revoked_body_triggers(connection)
    _ensure_body_owner_update_trigger(connection)
    _ensure_body_revoke_update_trigger(connection)


def start_embodiment_lease_v2(
    connection: sqlite3.Connection,
    *,
    elfie_id: str,
    body_id: str | None,
    state: str,
    lease_expires_at: str | None,
) -> TransitionLeaseRow:
    """Insert the first versioned lease row for an Elfie."""
    _ensure_body_can_receive_lease(connection, elfie_id, body_id)
    existing = connection.execute(
        "SELECT 1 FROM embodiment_sessions_v2 WHERE elfie_id = ?",
        (elfie_id,),
    ).fetchone()
    if existing is not None:
        raise TransitionLeaseConflict(f"lease already exists for Elfie {elfie_id}")
    connection.execute(
        """
        INSERT INTO embodiment_sessions_v2
            (elfie_id, body_id, state, lease_expires_at, lease_version)
        VALUES (?, ?, ?, ?, 1)
        """,
        (elfie_id, body_id, state, lease_expires_at),
    )
    return TransitionLeaseRow(elfie_id, body_id, state, lease_expires_at, 1)


def update_embodiment_lease_v2(
    connection: sqlite3.Connection,
    *,
    elfie_id: str,
    expected_lease_version: int,
    body_id: str | None,
    state: str,
    lease_expires_at: str | None,
) -> TransitionLeaseRow:
    """Advance one lease row only when the caller observed the current version."""
    _ensure_body_can_receive_lease(connection, elfie_id, body_id)
    cursor = connection.execute(
        """
        UPDATE embodiment_sessions_v2
        SET body_id = ?,
            state = ?,
            lease_expires_at = ?,
            lease_version = lease_version + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE elfie_id = ? AND lease_version = ?
        """,
        (body_id, state, lease_expires_at, elfie_id, expected_lease_version),
    )
    if cursor.rowcount != 1:
        raise TransitionLeaseConflict("stale embodiment lease write rejected")
    row = connection.execute(
        """
        SELECT elfie_id, body_id, state, lease_expires_at, lease_version
        FROM embodiment_sessions_v2
        WHERE elfie_id = ?
        """,
        (elfie_id,),
    ).fetchone()
    return _row_to_lease(row)


def _ensure_body_can_receive_lease(
    connection: sqlite3.Connection,
    elfie_id: str,
    body_id: str | None,
) -> None:
    if body_id is None:
        return
    row = connection.execute(
        "SELECT owner_elfie_id, status FROM external_bodies WHERE body_id = ?",
        (body_id,),
    ).fetchone()
    if row is None:
        raise TransitionLeaseConflict(f"external body not found: {body_id}")
    if str(row["status"]) == "revoked":
        raise TransitionLeaseConflict(f"external body is revoked: {body_id}")
    if str(row["owner_elfie_id"]) != elfie_id:
        raise TransitionLeaseConflict("external body belongs to another Elfie")


def _ensure_revoked_body_triggers(connection: sqlite3.Connection) -> None:
    for action in ("INSERT", "UPDATE OF body_id, elfie_id"):
        trigger_name = f"trg_embodiment_v2_body_not_revoked_{action.lower().split()[0]}"
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {trigger_name}
            BEFORE {action} ON embodiment_sessions_v2
            WHEN NEW.body_id IS NOT NULL
             AND EXISTS (
                SELECT 1 FROM external_bodies
                WHERE body_id = NEW.body_id AND status = 'revoked'
             )
            BEGIN
                SELECT RAISE(ABORT, 'revoked body cannot receive embodiment lease');
            END
            """
        )
        owner_trigger_name = (
            f"trg_embodiment_v2_body_same_owner_{action.lower().split()[0]}"
        )
        connection.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS {owner_trigger_name}
            BEFORE {action} ON embodiment_sessions_v2
            WHEN NEW.body_id IS NOT NULL
             AND EXISTS (
                SELECT 1 FROM external_bodies
                WHERE body_id = NEW.body_id AND owner_elfie_id <> NEW.elfie_id
             )
            BEGIN
                SELECT RAISE(ABORT, 'body owner must match lease Elfie');
            END
            """
        )


def _ensure_body_owner_update_trigger(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_external_bodies_owner_matches_leases
        BEFORE UPDATE OF owner_elfie_id ON external_bodies
        WHEN EXISTS (
            SELECT 1 FROM embodiment_sessions_v2
            WHERE body_id = NEW.body_id AND elfie_id <> NEW.owner_elfie_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'body owner must match existing leases');
        END
        """
    )


def _ensure_body_revoke_update_trigger(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_external_bodies_revoke_requires_release
        BEFORE UPDATE OF status, revoked_at ON external_bodies
        WHEN (NEW.status = 'revoked' OR NEW.revoked_at IS NOT NULL)
         AND EXISTS (
            SELECT 1 FROM embodiment_sessions_v2
            WHERE body_id = NEW.body_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'body must be released before revoke');
        END
        """
    )


def _row_to_lease(row: sqlite3.Row) -> TransitionLeaseRow:
    return TransitionLeaseRow(
        elfie_id=str(row["elfie_id"]),
        body_id=str(row["body_id"]) if row["body_id"] is not None else None,
        state=str(row["state"]),
        lease_expires_at=(
            str(row["lease_expires_at"])
            if row["lease_expires_at"] is not None
            else None
        ),
        lease_version=int(row["lease_version"]),
    )
