"""Final knowledge store entity-table contract tests."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from elfie.brain.memory.knowledge_store import (
    KnowledgeStore,
    KnowledgeStorePathError,
)

EXPECTED_TABLES = {
    "entities",
    "people",
    "known_elfies",
    "concepts",
    "places",
    "events",
    "entity_edges",
    "memory_notes",
    "source_evidence_links",
}


def _insert_entity(
    connection: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
) -> None:
    connection.execute(
        "INSERT INTO entities (entity_id, entity_type, name) VALUES (?, ?, ?)",
        (entity_id, entity_type, entity_id),
    )


def test_creates_exact_final_tables_and_private_database(tmp_path: Path) -> None:
    """Given a final path, When opened, Then only nine private tables exist."""
    db_path = tmp_path / "memory" / "knowledge.sqlite"

    with KnowledgeStore(db_path) as store:
        tables = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert tables == EXPECTED_TABLES
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_schema_initialization_is_idempotent(tmp_path: Path) -> None:
    """Given an initialized DB, When reopened, Then the same schema remains."""
    db_path = tmp_path / "knowledge.sqlite"

    with KnowledgeStore(db_path):
        pass
    with KnowledgeStore(db_path) as store:
        tables = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert tables == EXPECTED_TABLES


def test_rejects_non_final_filename_and_symlink(tmp_path: Path) -> None:
    """Given unsafe targets, When opened, Then no alternate DB is accepted."""
    target = tmp_path / "real.sqlite"
    target.touch()
    link = tmp_path / "knowledge.sqlite"
    link.symlink_to(target)

    with pytest.raises(KnowledgeStorePathError):
        KnowledgeStore(tmp_path / "graph_memory.db")
    with pytest.raises(KnowledgeStorePathError):
        KnowledgeStore(link)


def test_direct_sql_enforces_json_type_scores_and_foreign_keys() -> None:
    """Given the schema, When invalid entities are inserted, Then SQLite rejects."""
    with KnowledgeStore.in_memory() as store:
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO entities "
                "(entity_id, entity_type, name, aliases_json) VALUES (?, ?, ?, ?)",
                ("bad-json", "person", "Owner", "not-json"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert_entity(store.connection, "bad-type", "animal")
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO entities "
                "(entity_id, entity_type, name, confidence) VALUES (?, ?, ?, ?)",
                ("bad-score", "person", "Owner", 1.2),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO people (entity_id) VALUES (?)",
                ("missing",),
            )


def test_direct_sql_enforces_single_owner_self_and_known_elfie_id() -> None:
    """Given valid entities, When uniqueness is violated, Then writes fail."""
    with KnowledgeStore.in_memory() as store:
        for entity_id, entity_type in (
            ("owner-1", "person"),
            ("owner-2", "person"),
            ("self-1", "elfie"),
            ("self-2", "elfie"),
        ):
            _insert_entity(store.connection, entity_id, entity_type)

        store.connection.execute(
            "INSERT INTO people (entity_id, is_owner) VALUES (?, 1)",
            ("owner-1",),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO people (entity_id, is_owner) VALUES (?, 1)",
                ("owner-2",),
            )
        store.connection.execute(
            "INSERT INTO known_elfies (entity_id, elfie_id, is_self) VALUES (?, ?, 1)",
            ("self-1", "12345678"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO known_elfies (entity_id, elfie_id, is_self) "
                "VALUES (?, ?, 1)",
                ("self-2", "87654321"),
            )
