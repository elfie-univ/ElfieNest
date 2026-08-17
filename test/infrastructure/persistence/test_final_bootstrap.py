"""Root Infrastructure activation tests for the final storage contract."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.orchestration.lifecycle.ports import DataHomeState
from infrastructure.persistence.nest_db import store as nest_store
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database
from infrastructure.persistence.nest_db.store import (
    LegacyDataRootError,
    init_db,
    inspect_data_home,
    repair_data_home,
)

_FINAL_ROOT_TABLES = {
    "device_audit_events",
    "elfies",
    "embodiment_sessions",
    "external_bodies",
    "food_packages",
    "local_installations",
    "nest_settings",
    "sessions",
    "users",
}


def test_init_db_activates_only_the_final_nine_table_contract(
    tmp_path: Path,
) -> None:
    # Given: an empty explicit product data root.
    db_path = tmp_path / "data" / "nest.db"

    # When: the product database bootstrap runs twice.
    init_db(str(db_path))
    init_db(str(db_path))

    # Then: only the final root tables exist.
    with sqlite3.connect(db_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert tables == _FINAL_ROOT_TABLES


def test_init_db_rejects_legacy_database_without_changing_bytes(
    tmp_path: Path,
) -> None:
    # Given: a legacy database in an explicit disposable root.
    db_path = tmp_path / "nest.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE elfie_registry (elfie_id TEXT PRIMARY KEY)")
    before = db_path.read_bytes()

    # When: final bootstrap inspects the selected root.
    with pytest.raises(
        LegacyDataRootError,
        match="数据库结构与当前版本不兼容",
    ):
        init_db(str(db_path))

    # Then: detection is read-only and does not create final directories.
    assert db_path.read_bytes() == before
    assert set(tmp_path.iterdir()) == {db_path}


def test_partial_current_table_contract_is_repaired_in_place(
    tmp_path: Path,
) -> None:
    # Given: all current table names, but an old/partial set of columns.
    home = tmp_path / "data"
    home.mkdir()
    db_path = home / "nest.db"
    create_final_nest_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX idx_elfies_home_anchor_id")
        connection.execute("ALTER TABLE elfies DROP COLUMN home_anchor_id")
        connection.commit()

    # When: the read-only inspection and the narrow in-place repair run.
    inspection = inspect_data_home(home)
    repaired = repair_data_home(home)

    # Then: the additive field is restored without creating a recovery copy.
    assert inspection.state is DataHomeState.PARTIAL
    assert inspection.recoverable is False
    assert "elfies.home_anchor_id" in inspection.detail
    assert repaired.state is DataHomeState.READY
    assert not (tmp_path / "data-backups").exists()
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(elfies)")}
    assert "home_anchor_id" in columns


def test_ready_root_skips_repair_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a root that already satisfies the current contract.
    home = tmp_path / "data"
    home.mkdir()
    create_final_nest_database(home / "nest.db")

    # When: the lifecycle preparation runs.
    def fail_if_called(_: Path) -> Path:
        raise AssertionError("READY roots must not re-run additive repair")

    monkeypatch.setattr(nest_store, "repair_final_nest_database", fail_if_called)
    repaired = repair_data_home(home)

    # Then: the existing ready root proceeds without repair work.
    assert repaired.state is DataHomeState.READY


def test_partial_root_with_empty_database_is_repaired_without_deleting_residuals(
    tmp_path: Path,
) -> None:
    # Given: startup created an empty database and left only known runtime files.
    home = tmp_path / "data"
    home.mkdir()
    (home / "nest.db").touch()
    residual = home / "runtime" / "ollama" / "services.json"
    residual.parent.mkdir(parents=True)
    residual.write_text("{}", encoding="utf-8")

    # When: the lifecycle data-root preparation runs.
    inspection = inspect_data_home(home)
    repaired = repair_data_home(home)

    # Then: current storage and directories exist, while residual data is kept.
    assert inspection.state is DataHomeState.PARTIAL
    assert repaired.state is DataHomeState.READY
    assert residual.read_text(encoding="utf-8") == "{}"
    assert not (home.parent / "data-backups").exists()
    with sqlite3.connect(home / "nest.db") as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert tables == _FINAL_ROOT_TABLES


def test_missing_current_table_is_created_in_place(tmp_path: Path) -> None:
    # Given: a valid current database whose one table was left out.
    home = tmp_path / "data"
    db_path = home / "nest.db"
    home.mkdir()
    create_final_nest_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE food_packages")
        connection.commit()

    # When: the selected root is prepared.
    assert inspect_data_home(home).state is DataHomeState.PARTIAL
    repaired = repair_data_home(home)

    # Then: only the missing current table is restored and the root is ready.
    assert repaired.state is DataHomeState.READY
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert tables == _FINAL_ROOT_TABLES


def test_unsupported_missing_column_stays_blocked(tmp_path: Path) -> None:
    # Given: a current database missing a required timestamp column.
    home = tmp_path / "data"
    db_path = home / "nest.db"
    home.mkdir()
    create_final_nest_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("ALTER TABLE users DROP COLUMN updated_at")
        connection.commit()

    # Then: the narrow repair refuses to guess a non-additive contract.
    inspection = inspect_data_home(home)
    assert inspection.state is DataHomeState.LEGACY
    assert "users.updated_at" in inspection.detail
    with pytest.raises(LegacyDataRootError, match="数据库结构与当前版本不兼容"):
        init_db(str(db_path))


def test_init_db_rejects_retired_root_entries_before_creating_database(
    tmp_path: Path,
) -> None:
    # Given: a retired directory from the old data layout.
    retired = tmp_path / "cache"
    retired.mkdir()
    marker = retired / "marker.txt"
    marker.write_text("keep", encoding="utf-8")

    # When: final bootstrap inspects the selected root.
    with pytest.raises(LegacyDataRootError):
        init_db(str(tmp_path / "nest.db"))

    # Then: the old root is untouched and no database is created.
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "nest.db").exists()
