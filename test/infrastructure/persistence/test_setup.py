from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.store import init_db
from infrastructure.persistence.setup import SQLiteSetupAdapter


def test_setup_reads_are_read_only_when_the_installation_row_is_absent(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)

    before = _row_count(db_path)
    installation = adapter.read_installation()
    draft = adapter.read_draft()
    after = _row_count(db_path)

    assert before == after == 0
    assert installation.status == "not_started"
    assert draft.owner_configured is False


def test_first_draft_write_creates_the_single_setup_row(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)
    saved = adapter.save_offline_draft(use_local_ollama=False, model_id=None)
    assert saved.offline_configured is True
    assert _row_count(db_path) == 1


def test_recovery_is_read_only_when_no_setup_row_exists(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)

    adapter.recover_running("interrupted")

    assert _row_count(db_path) == 0


def _row_count(db_path: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute("SELECT count(*) FROM local_installations").fetchone()[0]
        )
