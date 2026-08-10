"""External-body credentials are one-time, hashed at rest, and revocable."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.bodies.ports import BodiesPortCredentialRejected
from app.infrastructure.persistence.store import get_db, init_db
from infrastructure.persistence.bodies import SQLiteBodiesAdapter


def _adapter_with_owner(tmp_path: Path) -> SQLiteBodiesAdapter:
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
    return SQLiteBodiesAdapter(db_path)


def test_enrolled_body_authenticates_without_storing_its_secret(
    tmp_path: Path,
) -> None:
    adapter = _adapter_with_owner(tmp_path)
    db_path = str(tmp_path / "nest.db")

    credential = adapter.enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name="客厅玩具",
        body_type="toy",
    )
    token = f"{credential.body_id}.{credential.secret}"
    record = adapter.authenticate(token)
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


def test_rotate_and_revoke_invalidate_old_body_credentials(tmp_path: Path) -> None:
    adapter = _adapter_with_owner(tmp_path)
    credential = adapter.enroll(
        owner_user_id=1,
        elfie_id="00000001",
        display_name="客厅玩具",
        body_type="toy",
    )
    old_token = f"{credential.body_id}.{credential.secret}"

    replacement = adapter.rotate(
        owner_user_id=1,
        elfie_id="00000001",
        body_id=credential.body_id,
    )
    with pytest.raises(BodiesPortCredentialRejected):
        adapter.authenticate(old_token)
    replacement_token = f"{replacement.body_id}.{replacement.secret}"
    assert adapter.authenticate(replacement_token).body_id == credential.body_id

    adapter.revoke(
        owner_user_id=1,
        elfie_id="00000001",
        body_id=credential.body_id,
    )
    with pytest.raises(BodiesPortCredentialRejected):
        adapter.authenticate(replacement_token)
