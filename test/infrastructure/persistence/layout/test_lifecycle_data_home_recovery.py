"""Safety tests for the user-facing data-root recovery workflow."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.orchestration.lifecycle.ports import DataHomeState
from infrastructure.persistence.layout.lifecycle_data_home import (
    LifecycleDataHomeAdapter,
)


def test_inspect_classifies_legacy_root_without_writing_to_it(tmp_path: Path) -> None:
    home = tmp_path / "elfienest"
    home.mkdir()
    (home / "backups").mkdir()
    (home / "user-notes.txt").write_text("keep me", encoding="utf-8")

    inspection = LifecycleDataHomeAdapter().inspect(home)

    assert inspection.state is DataHomeState.LEGACY
    assert inspection.home == home.resolve()
    assert inspection.recoverable is True
    assert (home / "user-notes.txt").read_text(encoding="utf-8") == "keep me"


def test_recover_moves_legacy_root_and_creates_a_fresh_active_root(
    tmp_path: Path,
) -> None:
    home = tmp_path / "elfienest"
    home.mkdir()
    (home / "backups").mkdir()
    (home / "user-notes.txt").write_text("keep me", encoding="utf-8")
    with sqlite3.connect(home / "nest.db") as connection:
        connection.execute("CREATE TABLE legacy_users (id INTEGER PRIMARY KEY)")
        connection.commit()

    adapter = LifecycleDataHomeAdapter()
    result = adapter.recover(home)

    assert result.home == home.resolve()
    assert result.backup_home.is_dir()
    assert (result.backup_home / "user-notes.txt").read_text(encoding="utf-8") == "keep me"
    assert (result.backup_home / "nest.db").is_file()
    assert adapter.inspect(home).state is DataHomeState.READY
    assert not (home / "backups").exists()
