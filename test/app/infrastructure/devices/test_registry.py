"""Device secrets are one-time output, hashed at rest, and revocable."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.infrastructure.devices import DeviceRegistry
from app.infrastructure.devices.registry import DeviceCredentialError
from app.infrastructure.persistence.store import get_db, init_db


def _registry_with_owner(tmp_path: Path) -> DeviceRegistry:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (id, account_id, password_hash, role) VALUES (1, ?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id, name, owner_user_id, species, adopted_at, status
               ) VALUES ('00000001', '测试精灵', 1, 'test', CURRENT_TIMESTAMP, 'offline')"""
        )
        connection.commit()
    return DeviceRegistry(db_path)


def test_enrolled_device_authenticates_with_a_secret_not_stored_in_database(
    tmp_path: Path,
) -> None:
    registry = _registry_with_owner(tmp_path)
    db_path = str(tmp_path / "nest.db")

    credential = registry.enroll("00000001", "客厅玩具", "toy")
    record = registry.authenticate(credential.bearer_token)
    with get_db(db_path) as connection:
        saved_hash = str(
            connection.execute(
                "SELECT secret_hash FROM external_bodies WHERE body_id = ?",
                (credential.body_id,),
            ).fetchone()["secret_hash"]
        )

    assert record.display_name == "客厅玩具"
    assert credential.secret not in saved_hash
    assert credential.secret not in str(record)


def test_rotate_and_revoke_invalidate_old_device_credentials(tmp_path: Path) -> None:
    registry = _registry_with_owner(tmp_path)
    credential = registry.enroll("00000001", "客厅玩具", "toy")

    replacement = registry.rotate("00000001", credential.body_id)
    with pytest.raises(DeviceCredentialError):
        registry.authenticate(credential.bearer_token)
    assert registry.authenticate(replacement.bearer_token).body_id == credential.body_id

    registry.revoke("00000001", credential.body_id)
    with pytest.raises(DeviceCredentialError):
        registry.authenticate(replacement.bearer_token)
