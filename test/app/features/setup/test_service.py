from __future__ import annotations

from pathlib import Path

import pytest

from app.features.setup.service import (
    needs_setup,
    save_offline_setup_draft,
)
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db, init_db

from .test_support import create_test_owner


def test_create_first_owner_from_hash_does_not_create_session(tmp_path: Path) -> None:
    # Given
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    # When
    account = create_test_owner(db_path, display_name="Owner")

    # Then
    with get_db(db_path) as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        owner = conn.execute(
            "SELECT account_id, display_name FROM users WHERE id = ?",
            (account.user_id,),
        ).fetchone()
    assert account.account_id == "owner"
    assert account.display_name == "Owner"
    assert account.role == "owner"
    assert owner["account_id"] == "owner"
    assert owner["display_name"] == "Owner"
    assert session_count == 0


def test_owner_creation_advances_only_first_setup_step(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    create_test_owner(db_path)

    record = SetupInstallRepository(db_path).get()
    assert record.owner_user_id is not None
    assert record.status == "in_progress"
    assert record.install_step is None
    assert needs_setup(db_path)


def test_setup_uses_only_final_installation_table(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_test_owner(db_path)
    repository = SetupInstallRepository(db_path)
    repository.save_offline_draft(use_local_ollama=False, model_id=None)
    repository.begin_or_resume()

    with get_db(db_path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        row = conn.execute(
            "SELECT owner_user_id, status, install_step "
            "FROM local_installations WHERE installation_id='local'"
        ).fetchone()
    assert row is not None
    assert row["owner_user_id"] is not None
    assert row["status"] == "in_progress"
    assert row["install_step"] == 2
    assert "setup_progress" not in tables


def test_offline_draft_model_validation_stays_in_setup_feature(tmp_path: Path) -> None:
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)

    with pytest.raises(ValueError, match="固定的本地模型"):
        save_offline_setup_draft(
            db_path,
            use_local_ollama=True,
            model_id="not-a-supported-model",
        )
