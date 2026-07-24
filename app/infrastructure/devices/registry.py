"""Persist local device identities without retaining their raw bearer secret."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from app.infrastructure.persistence.store import get_db, hash_password, verify_password


class DeviceCredentialError(RuntimeError):
    """Raised for malformed, revoked, or invalid machine credentials."""


@dataclass(frozen=True)
class DeviceCredential:
    """One-time enrollment material; never write its secret to audit storage."""

    device_id: str
    secret: str

    @property
    def bearer_token(self) -> str:
        return f"{self.device_id}.{self.secret}"


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    owner_user_id: int
    display_name: str
    revoked: bool
    last_heartbeat_at: float | None


class DeviceRegistry:
    """Single persistence boundary for the LAN device credential lifecycle."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def enroll(self, owner_user_id: int, display_name: str) -> DeviceCredential:
        normalized = display_name.strip()
        if not normalized:
            raise ValueError("设备名称不能为空")
        device_id = f"dev_{secrets.token_hex(12)}"
        secret = secrets.token_urlsafe(32)
        with get_db(self._db_path) as connection:
            connection.execute(
                """INSERT INTO devices (device_id, owner_user_id, display_name, secret_hash)
                   VALUES (?, ?, ?, ?)""",
                (device_id, owner_user_id, normalized, hash_password(secret)),
            )
            _audit(connection, device_id, "enrolled")
            connection.commit()
        return DeviceCredential(device_id=device_id, secret=secret)

    def rotate(self, owner_user_id: int, device_id: str) -> DeviceCredential:
        self._owned_record(owner_user_id, device_id)
        secret = secrets.token_urlsafe(32)
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE devices SET secret_hash = ?, revoked_at = NULL,
                   updated_at = CURRENT_TIMESTAMP WHERE device_id = ?""",
                (hash_password(secret), device_id),
            )
            _audit(connection, device_id, "rotated")
            connection.commit()
        return DeviceCredential(device_id=device_id, secret=secret)

    def revoke(self, owner_user_id: int, device_id: str) -> None:
        self._owned_record(owner_user_id, device_id)
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE devices SET revoked_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP WHERE device_id = ?""",
                (device_id,),
            )
            _audit(connection, device_id, "revoked")
            connection.commit()

    def list_for_owner(self, owner_user_id: int) -> list[DeviceRecord]:
        with get_db(self._db_path) as connection:
            rows = connection.execute(
                """SELECT device_id, owner_user_id, display_name, revoked_at,
                          last_heartbeat_at FROM devices
                   WHERE owner_user_id = ? ORDER BY created_at DESC""",
                (owner_user_id,),
            ).fetchall()
        return [_record(row) for row in rows]

    def authenticate(self, bearer_token: str) -> DeviceRecord:
        device_id, secret = _parse_bearer_token(bearer_token)
        with get_db(self._db_path) as connection:
            row = connection.execute(
                """SELECT device_id, owner_user_id, display_name, secret_hash, revoked_at,
                          last_heartbeat_at FROM devices WHERE device_id = ?""",
                (device_id,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise DeviceCredentialError("设备凭证无效或已撤销")
        if not verify_password(secret, str(row["secret_hash"])):
            raise DeviceCredentialError("设备凭证无效或已撤销")
        return _record(row)

    def heartbeat(self, device_id: str) -> None:
        with get_db(self._db_path) as connection:
            connection.execute(
                """UPDATE devices SET last_heartbeat_at = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE device_id = ? AND revoked_at IS NULL""",
                (time.time(), device_id),
            )
            _audit(connection, device_id, "heartbeat")
            connection.commit()

    def record_protocol_event(self, device_id: str, event_type: str) -> None:
        """Append a non-secret protocol audit event for a valid device frame."""
        with get_db(self._db_path) as connection:
            _audit(connection, device_id, event_type)
            connection.commit()

    def _owned_record(self, owner_user_id: int, device_id: str) -> DeviceRecord:
        for record in self.list_for_owner(owner_user_id):
            if record.device_id == device_id:
                return record
        raise DeviceCredentialError("设备不存在")


def _parse_bearer_token(value: str) -> tuple[str, str]:
    device_id, separator, secret = value.partition(".")
    if not separator or not device_id.startswith("dev_") or not secret:
        raise DeviceCredentialError("设备凭证格式无效")
    return device_id, secret


def _record(row) -> DeviceRecord:
    return DeviceRecord(
        device_id=str(row["device_id"]),
        owner_user_id=int(row["owner_user_id"]),
        display_name=str(row["display_name"]),
        revoked=row["revoked_at"] is not None,
        last_heartbeat_at=(
            float(row["last_heartbeat_at"])
            if row["last_heartbeat_at"] is not None
            else None
        ),
    )


def _audit(connection, device_id: str, event_type: str) -> None:
    connection.execute(
        "INSERT INTO device_audit_events (device_id, event_type) VALUES (?, ?)",
        (device_id, event_type),
    )
