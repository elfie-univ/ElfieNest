"""Card 18 cutover rollback gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_runtime.storage.config_store import write_yaml_mapping
from app.features.setup.progress import complete_setup_step, get_setup_progress
from app.features.setup.service import create_first_owner_account
from app.infrastructure.persistence.store import get_db, init_db


@pytest.mark.parametrize(
    ("legacy_values", "config", "message"),
    (
        (("bound_existing", "http://127.0.0.1:11434", None, None), {}, "endpoint"),
        (
            ("install_official", "http://127.0.0.1:11434", None, None),
            {"providers": {"ollama": {"api_base": "http://127.0.0.1:9999"}}},
            "endpoint",
        ),
        (
            ("skipped", None, "configured", "ollama/qwen2.5:0.5b"),
            {"providers": {"ollama": {"selected_model": "ollama/other"}}},
            "model",
        ),
    ),
)
def test_cutover_rolls_back_when_config_does_not_express_legacy_decision(
    tmp_path: Path,
    legacy_values: tuple[str, str | None, str | None, str | None],
    config: dict[str, dict[str, dict[str, str]]],
    message: str,
) -> None:
    # Given: legacy decisions disagree with the current sibling config.yaml.
    db_path = init_db(str(tmp_path / "nest.db"))
    write_yaml_mapping(tmp_path / "config.yaml", config)
    with get_db(db_path) as connection:
        connection.execute(
            """
            UPDATE setup_progress
            SET current_step = 5, ollama_decision = ?, ollama_endpoint = ?,
                model_decision = ?, model_reference = ?
            WHERE singleton_id = 1
            """,
            legacy_values,
        )
        legacy_before = tuple(
            connection.execute(
                "SELECT * FROM setup_progress WHERE singleton_id = 1"
            ).fetchone()
        )
        connection.commit()

    # When/Then: validation aborts the whole DDL + copy transaction.
    with pytest.raises(RuntimeError, match=message):
        get_setup_progress(db_path)
    with get_db(db_path) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'local_installations'"
        ).fetchone()
        legacy_after = tuple(
            connection.execute(
                "SELECT * FROM setup_progress WHERE singleton_id = 1"
            ).fetchone()
        )
    assert table is None
    assert legacy_after == legacy_before


def test_cutover_rolls_back_when_legacy_installation_is_missing(
    tmp_path: Path,
) -> None:
    # Given: a corrupted legacy root without its required singleton.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute("DELETE FROM setup_progress WHERE singleton_id = 1")
        connection.commit()

    # When/Then: the cutover refuses to invent history and rolls back its DDL.
    with pytest.raises(RuntimeError, match="安装记录"):
        get_setup_progress(db_path)
    with get_db(db_path) as connection:
        target_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'local_installations'"
        ).fetchone()
    assert target_table is None


def test_cutover_rolls_back_when_legacy_task_state_is_invalid(tmp_path: Path) -> None:
    # Given: a damaged legacy database bypassed its historical CHECK constraint.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE setup_progress SET task_state = 'invented' WHERE singleton_id = 1"
        )
        connection.commit()

    # When/Then: typed validation rejects it before any final DDL can commit.
    with pytest.raises(RuntimeError, match="非法"):
        get_setup_progress(db_path)
    with get_db(db_path) as connection:
        target_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'local_installations'"
        ).fetchone()
    assert target_table is None


def test_existing_installation_rejects_unexpressed_ollama_endpoint(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    create_first_owner_account(db_path, username="owner", password="secret123")

    with pytest.raises(RuntimeError, match="endpoint"):
        complete_setup_step(
            db_path,
            step=2,
            decision="bound_existing",
            ollama_endpoint="http://127.0.0.1:11434",
        )

    assert get_setup_progress(db_path).current_step == 2
