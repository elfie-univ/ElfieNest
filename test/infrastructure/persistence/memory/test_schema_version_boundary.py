"""Schema v1 initializes fresh stores and rejects old stores without mutation."""

import sqlite3
from pathlib import Path

import pytest

from infrastructure.persistence.memory.schema import SCHEMA_VERSION
from infrastructure.persistence.memory.sqlite_memory_store import (
    MemoryStoreSchemaError,
    SQLiteMemoryStoreAdapter,
)


def test_fresh_store_initializes_memory_schema_v1(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(path) as store:
        assert store.schema_version == 1
        assert store.schema_version == SCHEMA_VERSION


def test_old_store_is_rejected_with_exact_path_and_no_mutation(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE episodes (episode_id TEXT PRIMARY KEY, content_text TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO episodes VALUES ('keep-me', 'original data')")
        connection.execute("PRAGMA user_version=9")
        connection.commit()

    before_bytes = path.read_bytes()
    with sqlite3.connect(path) as connection:
        before_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        before_row = connection.execute(
            "SELECT episode_id, content_text FROM episodes"
        ).fetchone()

    with pytest.raises(MemoryStoreSchemaError) as error:
        SQLiteMemoryStoreAdapter(path)
    assert str(path) in str(error.value)

    assert path.read_bytes() == before_bytes
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 9
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            == before_tables
        )
        assert (
            connection.execute(
                "SELECT episode_id, content_text FROM episodes"
            ).fetchone()
            == before_row
            == ("keep-me", "original data")
        )
