"""Final external-body credentials, ownership, heartbeat, revoke, and audit."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app.infrastructure.persistence.store import get_db


class DeviceCredentialError(RuntimeError):
    """Raised for malformed, revoked, cross-owner, or invalid body credentials."""


@dataclass(frozen=True)
class DeviceCredential:
    """One-time body enrollment material; its raw secret is never persisted."""

    body_id: str
    secret: str

    @property
    def device_id(self) -> str:
        """Expose the transport-facing identifier used by the current gateway."""
        return self.body_id

    @property
    def bearer_token(self) -> str:
        return f"{self.body_id}.{self.secret}"


@dataclass(frozen=True)
class DeviceRecord:
    """One final external body without secret material."""

    body_id: str
    owner_elfie_id: str
    display_name: str
    body_type: str
    status: str
    last_heartbeat_at: str | None

    @property
    def device_id(self) -> str:
        """Expose the transport-facing identifier used by the current gateway."""
        return self.body_id

    @property
    def revoked(self) -> bool:
        return self.status == "revoked"


class ExternalBodyRepository:
    """Own the final ``external_bodies`` and body audit persistence boundary."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def enroll(
        self, *, owner_elfie_id: str, display_name: str, body_type: str
    ) -> DeviceCredential:
        """Register a body with an explicit Elfie owner and one-time secret."""
        normalized_name = display_name.strip()
        normalized_type = body_type.strip()
        if not normalized_name or not normalized_type:
            raise DeviceCredentialError("body name and type must not be empty")
        body_id = f"body_{secrets.token_hex(12)}"
        secret = secrets.token_urlsafe(32)
        with get_db(self._db_path) as connection:
            try:
                connection.execute(
                    """INSERT INTO external_bodies(
                           body_id, owner_elfie_id, display_name, body_type,
                           secret_hash, status
                       ) VALUES (?, ?, ?, ?, ?, 'available')""",
                    (
                        body_id,
                        owner_elfie_id,
                        normalized_name,
                        normalized_type,
                        _secret_hash(secret),
                    ),
                )
                _audit(connection, body_id, "enrolled", {})
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise DeviceCredentialError("invalid body owner or registration") from error
        return DeviceCredential(body_id=body_id, secret=secret)

    def rotate(self, owner_elfie_id: str, body_id: str) -> DeviceCredential:
        """Replace one active body's secret without retaining the old secret."""
        record = self._owned_record(owner_elfie_id, body_id)
        if record.revoked:
            raise DeviceCredentialError("revoked body cannot rotate credentials")
        secret = secrets.token_urlsafe(32)
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE external_bodies SET secret_hash=?,
                   updated_at=CURRENT_TIMESTAMP WHERE body_id=?""",
                (_secret_hash(secret), body_id),
            )
            _audit(connection, body_id, "rotated", {})
            connection.commit()
        return DeviceCredential(body_id=body_id, secret=secret)

    def revoke(self, owner_elfie_id: str, body_id: str) -> None:
        """Revoke an explicitly owned body after its active lease is released."""
        self._owned_record(owner_elfie_id, body_id)
        with get_db(self._db_path) as connection:
            try:
                connection.execute(
                    """UPDATE external_bodies SET status='revoked',
                       revoked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                       WHERE body_id=?""",
                    (body_id,),
                )
                _audit(connection, body_id, "revoked", {})
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise DeviceCredentialError("body must be released before revoke") from error

    def list_for_owner(self, owner_elfie_id: str) -> list[DeviceRecord]:
        """List bodies for exactly one Elfie owner."""
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                """SELECT * FROM external_bodies WHERE owner_elfie_id=?
                   ORDER BY created_at, body_id""",
                (owner_elfie_id,),
            ).fetchall()
        return [_record(row) for row in rows]

    def authenticate(self, bearer_token: str) -> DeviceRecord:
        """Authenticate a non-revoked body using its hashed one-time secret."""
        body_id, secret = _parse_bearer_token(bearer_token)
        with get_db(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM external_bodies WHERE body_id=?", (body_id,)
            ).fetchone()
        if row is None or str(row["status"]) == "revoked":
            raise DeviceCredentialError("body credential is invalid or revoked")
        if not hmac.compare_digest(_secret_hash(secret), str(row["secret_hash"])):
            raise DeviceCredentialError("body credential is invalid or revoked")
        return _record(row)

    def heartbeat(self, body_id: str) -> None:
        """Record a heartbeat only for a non-revoked final body."""
        observed_at = datetime.now(timezone.utc).isoformat()
        with get_db(self._db_path) as connection:
            cursor = connection.execute(
                """UPDATE external_bodies SET last_heartbeat_at=?,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE body_id=? AND status<>'revoked'""",
                (observed_at, body_id),
            )
            if cursor.rowcount != 1:
                raise DeviceCredentialError("body is missing or revoked")
            _audit(connection, body_id, "heartbeat", {})
            connection.commit()

    def record_protocol_event(self, body_id: str, event_type: str) -> None:
        """Append a secret-free audit event for a validated protocol frame."""
        with get_db(self._db_path) as connection:
            try:
                _audit(connection, body_id, event_type, {})
                connection.commit()
            except sqlite3.IntegrityError as error:
                raise DeviceCredentialError("body is missing") from error

    def _owned_record(self, owner_elfie_id: str, body_id: str) -> DeviceRecord:
        with get_db(self._db_path) as connection:
            row = connection.execute(
                """SELECT * FROM external_bodies
                   WHERE body_id=? AND owner_elfie_id=?""",
                (body_id, owner_elfie_id),
            ).fetchone()
        if row is None:
            raise DeviceCredentialError("body does not belong to this Elfie")
        return _record(row)


def _parse_bearer_token(value: str) -> tuple[str, str]:
    body_id, separator, secret = value.partition(".")
    if not separator or not body_id.startswith("body_") or not secret:
        raise DeviceCredentialError("body credential format is invalid")
    return body_id, secret


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _record(row: sqlite3.Row) -> DeviceRecord:
    return DeviceRecord(
        body_id=str(row["body_id"]),
        owner_elfie_id=str(row["owner_elfie_id"]),
        display_name=str(row["display_name"]),
        body_type=str(row["body_type"]),
        status=str(row["status"]),
        last_heartbeat_at=(
            None
            if row["last_heartbeat_at"] is None
            else str(row["last_heartbeat_at"])
        ),
    )


def _audit(
    connection: sqlite3.Connection,
    body_id: str,
    event_type: str,
    details: dict[str, str],
) -> None:
    connection.execute(
        """INSERT INTO device_audit_events(body_id, event_type, detail_json)
           VALUES (?, ?, ?)""",
        (body_id, event_type, json.dumps(details, ensure_ascii=False)),
    )


__all__ = (
    "DeviceCredential",
    "DeviceCredentialError",
    "DeviceRecord",
    "ExternalBodyRepository",
)
