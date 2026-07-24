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
            "INSERT INTO users (id, username, password_hash, role) VALUES (1, ?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.commit()
    return DeviceRegistry(db_path)


def test_enrolled_device_authenticates_with_a_secret_not_stored_in_database(
    tmp_path: Path,
) -> None:
    registry = _registry_with_owner(tmp_path)
    db_path = str(tmp_path / "nest.db")

    credential = registry.enroll(1, "客厅玩具")
    record = registry.authenticate(credential.bearer_token)
    with get_db(db_path) as connection:
        saved_hash = str(
            connection.execute(
                "SELECT secret_hash FROM devices WHERE device_id = ?",
                (credential.device_id,),
            ).fetchone()["secret_hash"]
        )

    assert record.display_name == "客厅玩具"
    assert credential.secret not in saved_hash
    assert credential.secret not in str(record)


def test_rotate_and_revoke_invalidate_old_device_credentials(tmp_path: Path) -> None:
    registry = _registry_with_owner(tmp_path)
    credential = registry.enroll(1, "客厅玩具")

    replacement = registry.rotate(1, credential.device_id)
    with pytest.raises(DeviceCredentialError):
        registry.authenticate(credential.bearer_token)
    assert (
        registry.authenticate(replacement.bearer_token).device_id
        == credential.device_id
    )

    registry.revoke(1, credential.device_id)
    with pytest.raises(DeviceCredentialError):
        registry.authenticate(replacement.bearer_token)
