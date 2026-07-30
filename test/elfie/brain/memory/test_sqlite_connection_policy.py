"""SQLite connection policy tests for Elfie memory storage."""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from elfie.brain.memory.graph_storage import GraphStorage
from elfie.brain.memory.sqlite_connection import memory_sqlite_connection


def _app_import_offenders(source_paths: list[Path]) -> list[str]:
    """Return source paths that import the application layer."""
    offenders: list[str] = []
    for source_path in source_paths:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                module_root = node.module.split(".", 1)[0]
                if module_root == "app":
                    offenders.append(str(source_path))
            if isinstance(node, ast.Import):
                imported_roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if "app" in imported_roots:
                    offenders.append(str(source_path))
    return offenders


def test_memory_connection_uses_explicit_temp_path_row_factory_and_foreign_keys(
    tmp_path: Path,
) -> None:
    """Given an explicit temp path, When opening memory SQLite, Then policy is set."""
    db_path = tmp_path / "memory-policy.db"

    with memory_sqlite_connection(str(db_path)) as connection:
        assert connection.row_factory is sqlite3.Row
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parents(id)"
            ")"
        )
        connection.execute("INSERT INTO parents (id) VALUES (1)")
        connection.commit()
        row = connection.execute("SELECT id FROM parents").fetchone()

    assert db_path.exists()
    assert row["id"] == 1


def test_memory_connection_rejects_foreign_key_violations(tmp_path: Path) -> None:
    """Given FK tables, When an orphan child is inserted, Then SQLite rejects it."""
    db_path = tmp_path / "memory-fk.db"
    with memory_sqlite_connection(str(db_path)) as connection:
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE children ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parents(id)"
            ")"
        )
        connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        with memory_sqlite_connection(str(db_path)) as connection:
            connection.execute(
                "INSERT INTO children (id, parent_id) VALUES (?, ?)",
                (1, 404),
            )


def test_memory_connection_rolls_back_on_exception_and_closes(
    tmp_path: Path,
) -> None:
    """Given committed schema, When a block raises, Then writes roll back and close."""
    db_path = tmp_path / "memory-rollback.db"
    with memory_sqlite_connection(str(db_path)) as connection:
        connection.execute("CREATE TABLE events (name TEXT NOT NULL)")
        connection.commit()

    with pytest.raises(RuntimeError):
        with memory_sqlite_connection(str(db_path)) as connection:
            connection.execute("INSERT INTO events (name) VALUES (?)", ("draft",))
            raise RuntimeError("force rollback")

    with memory_sqlite_connection(str(db_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert count == 0

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_graph_storage_uses_memory_connection_policy() -> None:
    """Given GraphStorage, When initialized, Then its connection has memory policy."""
    storage = GraphStorage(db_path=":memory:")
    try:
        assert storage.conn.row_factory is sqlite3.Row
        assert storage.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        storage.close()


def test_memory_modules_do_not_import_app() -> None:
    """Given memory modules, When imports are scanned, Then app is absent."""
    memory_root = Path("elfie/brain/memory")

    assert _app_import_offenders(list(memory_root.glob("*.py"))) == []


def test_memory_import_scanner_flags_app_submodule_import(tmp_path: Path) -> None:
    """Given a submodule app import, When scanned, Then it is rejected."""
    fixture = tmp_path / "bad_memory.py"
    fixture.write_text(
        "from app.infrastructure.persistence.store import get_db\n",
        encoding="utf-8",
    )

    assert _app_import_offenders([fixture]) == [str(fixture)]
