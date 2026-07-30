"""Card 18 one-time copy and legacy freeze guarantees."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_runtime.storage.config_store import write_yaml_mapping
from app.features.setup.progress import complete_setup_step, get_setup_progress
from app.features.setup.service import create_first_owner_account
from app.infrastructure.persistence.store import get_db, init_db


def test_expressed_decisions_copy_once_and_legacy_table_stays_frozen(
    tmp_path: Path,
) -> None:
    # Given: current config expresses every historical non-skipped decision.
    db_path = init_db(str(tmp_path / "nest.db"))
    write_yaml_mapping(
        tmp_path / "config.yaml",
        {
            "providers": {
                "ollama": {
                    "api_base": "http://127.0.0.1:11434",
                    "selected_model": "ollama/qwen2.5:0.5b",
                }
            }
        },
    )
    with get_db(db_path) as connection:
        connection.execute(
            """
            UPDATE setup_progress
            SET current_step = 5, ollama_decision = 'bound_existing',
                ollama_endpoint = 'http://127.0.0.1:11434',
                nest_completed_at = '2026-07-01T03:00:00Z',
                model_decision = 'configured',
                model_reference = 'ollama/qwen2.5:0.5b'
            WHERE singleton_id = 1
            """
        )
        legacy_before = tuple(
            connection.execute(
                "SELECT * FROM setup_progress WHERE singleton_id = 1"
            ).fetchone()
        )
        connection.commit()

    # When: later Setup writes finish through the target repository.
    get_setup_progress(db_path)
    complete_setup_step(db_path, step=5)

    # Then: the target advances while the complete legacy payload stays unchanged.
    with get_db(db_path) as connection:
        target = connection.execute(
            """
            SELECT setup_state, setup_step, completed_at
            FROM local_installations WHERE installation_id = 'local'
            """
        ).fetchone()
        legacy_after = tuple(
            connection.execute(
                "SELECT * FROM setup_progress WHERE singleton_id = 1"
            ).fetchone()
        )
    assert target is not None
    assert tuple(target[:2]) == ("completed", "food")
    assert target["completed_at"] is not None
    assert legacy_after == legacy_before


@pytest.mark.parametrize(
    "statement",
    (
        "INSERT INTO setup_progress (singleton_id) VALUES (1)",
        "UPDATE setup_progress SET current_step = 1 WHERE singleton_id = 1",
        "DELETE FROM setup_progress WHERE singleton_id = 1",
    ),
)
def test_legacy_installation_rejects_all_direct_writes(
    tmp_path: Path,
    statement: str,
) -> None:
    # Given: a successful cutover has frozen the legacy table at DB level.
    db_path = init_db(str(tmp_path / "nest.db"))
    get_setup_progress(db_path)

    # When/Then: no direct insert, update, or delete can mutate the source.
    with get_db(db_path) as connection, pytest.raises(
        sqlite3.IntegrityError,
        match="frozen",
    ):
        connection.execute(statement)


def test_new_owner_write_never_mutates_legacy_setup_progress(tmp_path: Path) -> None:
    # Given: a newly initialized root before the first repository access.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        legacy_before = tuple(
            connection.execute(
                "SELECT * FROM setup_progress WHERE singleton_id = 1"
            ).fetchone()
        )

    # When: Owner creation performs the first cutover and Setup write atomically.
    owner = create_first_owner_account(
        db_path,
        username="owner",
        password="secret123",
    )

    # Then: only the target row records the Owner milestone.
    with get_db(db_path) as connection:
        target = connection.execute(
            """
            SELECT owner_user_id, setup_state, setup_step
            FROM local_installations WHERE installation_id = 'local'
            """
        ).fetchone()
        legacy_after = tuple(
            connection.execute(
                "SELECT * FROM setup_progress WHERE singleton_id = 1"
            ).fetchone()
        )
    assert target is not None
    assert tuple(target) == (owner.user_id, "in_progress", "owner")
    assert legacy_after == legacy_before
