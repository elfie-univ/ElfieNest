"""Root Infrastructure activation tests for the final storage contract."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from infrastructure.persistence.nest_db.store import LegacyDataRootError, init_db

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
        match="检测到旧 ElfieNest 数据根；请先备份后重建。不会自动迁移或删除。",
    ):
        init_db(str(db_path))

    # Then: detection is read-only and does not create final directories.
    assert db_path.read_bytes() == before
    assert set(tmp_path.iterdir()) == {db_path}


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
