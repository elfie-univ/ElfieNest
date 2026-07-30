"""Persist external body credentials and their non-secret audit trail."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from dataclasses import dataclass
from sqlite3 import Connection, Row

from app.infrastructure.persistence.store import get_db


class DeviceCredentialError(RuntimeError):
    """Raised for malformed, revoked, or invalid body credentials."""


@dataclass(frozen=True)
class DeviceCredential:
    """One-time external body enrollment material."""

    body_id: str
    secret: str

    @property
    def bearer_token(self) -> str:
        return f"{self.body_id}.{self.secret}"


@dataclass(frozen=True)
class DeviceRecord:
    """Public external body record without its credential hash."""

    body_id: str
    owner_elfie_id: str
    display_name: str
    body_type: str
    status: str
    last_heartbeat_at: float | None


class DeviceRegistry:
    """Single persistence boundary for the external body lifecycle."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def enroll(
        self, owner_elfie_id: str, display_name: str, body_type: str
    ) -> DeviceCredential:
        normalized_name = display_name.strip()
        normalized_type = body_type.strip()
        if not normalized_name:
            raise ValueError("设备名称不能为空")
        if not normalized_type:
            raise ValueError("身体类型不能为空")
        body_id = f"body_{secrets.token_hex(12)}"
        secret = secrets.token_urlsafe(32)
        with get_db(self._db_path) as connection:
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
                    _hash_secret(secret),
                ),
            )
            _audit(connection, body_id, "enrolled")
            connection.commit()
        return DeviceCredential(body_id=body_id, secret=secret)

    def rotate(self, owner_elfie_id: str, body_id: str) -> DeviceCredential:
        self._owned_record(owner_elfie_id, body_id)
        secret = secrets.token_urlsafe(32)
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE external_bodies
                   SET secret_hash=?, updated_at=CURRENT_TIMESTAMP
                   WHERE body_id=?""",
                (_hash_secret(secret), body_id),
            )
            _audit(connection, body_id, "rotated")
            connection.commit()
        return DeviceCredential(body_id=body_id, secret=secret)

    def revoke(self, owner_elfie_id: str, body_id: str) -> None:
        self._owned_record(owner_elfie_id, body_id)
        with get_db(self._db_path) as connection:
            try:
                connection.execute(
                    """UPDATE external_bodies
                       SET status='revoked', revoked_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE body_id=?""",
                    (body_id,),
                )
            except sqlite3.IntegrityError as error:
                raise DeviceCredentialError("活动租约释放前不能撤销身体") from error
            _audit(connection, body_id, "revoked")
            connection.commit()

    def list_for_elfie(self, owner_elfie_id: str) -> list[DeviceRecord]:
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                """SELECT body_id, owner_elfie_id, display_name, body_type,
                          status, last_heartbeat_at
                   FROM external_bodies WHERE owner_elfie_id=?
                   ORDER BY created_at DESC""",
                (owner_elfie_id,),
            ).fetchall()
        return [_record(row) for row in rows]

    def authenticate(self, bearer_token: str) -> DeviceRecord:
        body_id, secret = _parse_bearer_token(bearer_token)
        with get_db(self._db_path) as connection:
            row = connection.execute(
                """SELECT body_id, owner_elfie_id, display_name, body_type,
                          secret_hash, status, last_heartbeat_at
                   FROM external_bodies WHERE body_id=?""",
                (body_id,),
            ).fetchone()
        if row is None or row["status"] == "revoked":
            raise DeviceCredentialError("设备凭证无效或已撤销")
        if not hmac.compare_digest(_hash_secret(secret), str(row["secret_hash"])):
            raise DeviceCredentialError("设备凭证无效或已撤销")
        return _record(row)

    def heartbeat(self, body_id: str) -> None:
        with get_db(self._db_path) as connection:
            cursor = connection.execute(
                """UPDATE external_bodies
                   SET last_heartbeat_at=?, updated_at=CURRENT_TIMESTAMP
                   WHERE body_id=? AND status<>'revoked'""",
                (time.time(), body_id),
            )
            if cursor.rowcount != 1:
                raise DeviceCredentialError("设备不存在或已撤销")
            _audit(connection, body_id, "heartbeat")
            connection.commit()

    def record_protocol_event(self, body_id: str, event_type: str) -> None:
        with get_db(self._db_path) as connection:
            _audit(connection, body_id, event_type)
            connection.commit()

    def _owned_record(self, owner_elfie_id: str, body_id: str) -> DeviceRecord:
        for record in self.list_for_elfie(owner_elfie_id):
            if record.body_id == body_id:
                return record
        raise DeviceCredentialError("设备不存在")


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _parse_bearer_token(value: str) -> tuple[str, str]:
    body_id, separator, secret = value.partition(".")
    if not separator or not body_id.startswith("body_") or not secret:
        raise DeviceCredentialError("设备凭证格式无效")
    return body_id, secret


def _record(row: Row) -> DeviceRecord:
    heartbeat = row["last_heartbeat_at"]
    return DeviceRecord(
        body_id=str(row["body_id"]),
        owner_elfie_id=str(row["owner_elfie_id"]),
        display_name=str(row["display_name"]),
        body_type=str(row["body_type"]),
        status=str(row["status"]),
        last_heartbeat_at=None if heartbeat is None else float(heartbeat),
    )


def _audit(connection: Connection, body_id: str, event_type: str) -> None:
    connection.execute(
        """INSERT INTO device_audit_events(body_id, event_type)
           VALUES (?, ?)""",
        (body_id, event_type),
    )
