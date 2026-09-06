from __future__ import annotations

import sqlite3
from pathlib import Path

from infrastructure.persistence.nest_db.store import init_db
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
    assert draft.bed_count == 12


def test_remote_food_decision_is_durable_without_writing_the_nest_default(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)

    adapter.save_owner_draft(
        account_id="owner",
        display_name="Owner",
        password_hash="hash",
    )
    saved = adapter.save_remote_draft(
        configured=True,
        connection_id="connection-openai",
    )
    reloaded = SQLiteSetupAdapter(db_path).read_draft()

    assert saved.remote_configured is True
    assert saved.remote_skipped is False
    assert saved.remote_connection_id == "connection-openai"
    assert saved.bed_count == 12
    assert saved.nest_configured is False
    assert reloaded == saved


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


def test_failed_installation_unlocks_the_draft_for_safe_retry(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)
    _complete_and_lock_draft(adapter)
    adapter.begin_or_resume()

    adapter.fail("model.download", "download timed out")

    assert adapter.read_installation().task_status == "failed"
    assert adapter.read_installation().last_error == "download timed out"
    assert adapter.read_draft().locked_at is None


def test_cancelled_installation_is_projected_and_unlocks_the_draft(
    tmp_path: Path,
) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)
    _complete_and_lock_draft(adapter)
    adapter.begin_or_resume()

    cancelled = adapter.cancel_installation()

    assert cancelled.task_status == "cancelled"
    assert cancelled.install_action == "cancelled"
    assert adapter.read_draft().locked_at is None


def test_recovery_unlocks_a_stale_failed_installation(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    adapter = SQLiteSetupAdapter(db_path)
    _complete_and_lock_draft(adapter)
    adapter.begin_or_resume()
    adapter.fail("model.download", "failed")
    adapter.lock_draft()

    adapter.recover_running("interrupted")

    assert adapter.read_installation().task_status == "failed"
    assert adapter.read_draft().locked_at is None


def _row_count(db_path: str) -> int:
    with sqlite3.connect(db_path) as connection:
        return int(
            connection.execute("SELECT count(*) FROM local_installations").fetchone()[0]
        )


def _complete_and_lock_draft(adapter: SQLiteSetupAdapter) -> None:
    adapter.save_owner_draft(
        account_id="owner",
        display_name=None,
        password_hash="hash",
    )
    adapter.save_remote_draft(configured=False, connection_id=None)
    adapter.save_nest_draft(bed_count=8)
    adapter.lock_draft()
