"""SQLite adapter for external-body relationships and independent credentials."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from sqlite3 import Connection, Row

from app.features.bodies.ports import (
    BodiesPortConflict,
    BodiesPortCredentialRejected,
    BodiesPortError,
    BodiesPortNotFound,
    BodyCredentialRecord,
    BodyRecord,
)

from .sqlite_connection import app_sqlite_connection


class SQLiteBodiesAdapter:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def list_for_elfie(
        self, *, owner_user_id: int, elfie_id: str
    ) -> tuple[BodyRecord, ...]:
        with app_sqlite_connection(self._db_path) as connection:
            self._require_owned_elfie(connection, owner_user_id, elfie_id)
            rows = connection.execute(
                """SELECT body_id, owner_elfie_id, display_name, body_type,
                          status, last_heartbeat_at
                   FROM external_bodies WHERE owner_elfie_id=?
                   ORDER BY created_at DESC""",
                (elfie_id,),
            ).fetchall()
        return tuple(_record(row) for row in rows)

    def enroll(
        self,
        *,
        owner_user_id: int,
        elfie_id: str,
        display_name: str,
        body_type: str,
    ) -> BodyCredentialRecord:
        body_id = f"body_{secrets.token_hex(12)}"
        secret = secrets.token_urlsafe(32)
        with app_sqlite_connection(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_owned_elfie(connection, owner_user_id, elfie_id)
            try:
                connection.execute(
                    """INSERT INTO external_bodies(
                           body_id, owner_elfie_id, display_name, body_type,
                           secret_hash, status
                       ) VALUES (?, ?, ?, ?, ?, 'available')""",
                    (
                        body_id,
                        elfie_id,
                        display_name,
                        body_type,
                        _hash_secret(secret),
                    ),
                )
                _audit(connection, body_id, "enrolled")
                connection.commit()
            except sqlite3.Error as error:
                connection.rollback()
                raise BodiesPortError("Unable to enroll body") from error
        return BodyCredentialRecord(body_id=body_id, secret=secret)

    def rotate(
        self, *, owner_user_id: int, elfie_id: str, body_id: str
    ) -> BodyCredentialRecord:
        secret = secrets.token_urlsafe(32)
        with app_sqlite_connection(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_owned_body(connection, owner_user_id, elfie_id, body_id)
            connection.execute(
                """UPDATE external_bodies
                   SET secret_hash=?, updated_at=CURRENT_TIMESTAMP
                   WHERE body_id=?""",
                (_hash_secret(secret), body_id),
            )
            _audit(connection, body_id, "rotated")
            connection.commit()
        return BodyCredentialRecord(body_id=body_id, secret=secret)

    def revoke(self, *, owner_user_id: int, elfie_id: str, body_id: str) -> None:
        with app_sqlite_connection(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_owned_body(connection, owner_user_id, elfie_id, body_id)
            try:
                connection.execute(
                    """UPDATE external_bodies
                       SET status='revoked', revoked_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE body_id=?""",
                    (body_id,),
                )
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise BodiesPortConflict("Active body cannot be revoked") from error
            _audit(connection, body_id, "revoked")
            connection.commit()

    def authenticate(self, bearer_token: str) -> BodyRecord:
        body_id, secret = _parse_bearer_token(bearer_token)
        with app_sqlite_connection(self._db_path) as connection:
            row = connection.execute(
                """SELECT body_id, owner_elfie_id, display_name, body_type,
                          secret_hash, status, last_heartbeat_at
                   FROM external_bodies WHERE body_id=?""",
                (body_id,),
            ).fetchone()
        if row is None or row["status"] == "revoked":
            raise BodiesPortCredentialRejected("Body credential rejected")
        if not hmac.compare_digest(_hash_secret(secret), str(row["secret_hash"])):
            raise BodiesPortCredentialRejected("Body credential rejected")
        return _record(row)

    def record_activity(self, body_id: str, activity: str) -> None:
        with app_sqlite_connection(self._db_path) as connection:
            if activity == "heartbeat":
                cursor = connection.execute(
                    """UPDATE external_bodies
                       SET last_heartbeat_at=?, updated_at=CURRENT_TIMESTAMP
                       WHERE body_id=? AND status<>'revoked'""",
                    (time.time(), body_id),
                )
                if cursor.rowcount != 1:
                    raise BodiesPortCredentialRejected("Body credential rejected")
            _audit(connection, body_id, activity)
            connection.commit()

    @staticmethod
    def _require_owned_elfie(
        connection: Connection, owner_user_id: int, elfie_id: str
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM elfies WHERE elfie_id=? AND owner_user_id=?",
            (elfie_id, owner_user_id),
        ).fetchone()
        if row is None:
            raise BodiesPortNotFound("Elfie not found")

    @classmethod
    def _require_owned_body(
        cls,
        connection: Connection,
        owner_user_id: int,
        elfie_id: str,
        body_id: str,
    ) -> None:
        cls._require_owned_elfie(connection, owner_user_id, elfie_id)
        row = connection.execute(
            """SELECT 1 FROM external_bodies
               WHERE body_id=? AND owner_elfie_id=?""",
            (body_id, elfie_id),
        ).fetchone()
        if row is None:
            raise BodiesPortNotFound("Body not found")


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _parse_bearer_token(value: str) -> tuple[str, str]:
    body_id, separator, secret = value.partition(".")
    if not separator or not body_id.startswith("body_") or not secret:
        raise BodiesPortCredentialRejected("Body credential rejected")
    return body_id, secret


def _record(row: Row) -> BodyRecord:
    heartbeat = row["last_heartbeat_at"]
    return BodyRecord(
        body_id=str(row["body_id"]),
        owner_elfie_id=str(row["owner_elfie_id"]),
        display_name=str(row["display_name"]),
        body_type=str(row["body_type"]),
        status=str(row["status"]),
        last_heartbeat_at=None if heartbeat is None else float(heartbeat),
    )


def _audit(connection: Connection, body_id: str, event_type: str) -> None:
    connection.execute(
        "INSERT INTO device_audit_events(body_id, event_type) VALUES (?, ?)",
        (body_id, event_type),
    )


__all__ = ("SQLiteBodiesAdapter",)
