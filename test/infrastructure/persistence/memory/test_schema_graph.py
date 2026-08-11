"""Final knowledge store graph, note, and evidence contract tests."""

from __future__ import annotations

import sqlite3

import pytest

from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def _insert_entity(connection: sqlite3.Connection, entity_id: str) -> None:
    connection.execute(
        "INSERT INTO entities (entity_id, entity_type, name) VALUES (?, ?, ?)",
        (entity_id, "concept", entity_id),
    )


def test_direct_sql_rejects_dangling_duplicate_and_invalid_edges() -> None:
    """Given two entities, When invalid edges are inserted, Then writes fail."""
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        _insert_entity(store.connection, "source")
        _insert_entity(store.connection, "target")
        store.connection.execute(
            "INSERT INTO entity_edges "
            "(edge_id, source_entity_id, target_entity_id, relation_type) "
            "VALUES (?, ?, ?, ?)",
            ("edge-1", "source", "target", "supports"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type) "
                "VALUES (?, ?, ?, ?)",
                ("edge-2", "source", "target", "supports"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type) "
                "VALUES (?, ?, ?, ?)",
                ("edge-3", "source", "missing", "supports"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type, weight) "
                "VALUES (?, ?, ?, ?, ?)",
                ("edge-4", "source", "target", "likes", -0.1),
            )


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/bad.md",
        "C:/Users/elfie/bad.md",
        "C:\\Users\\elfie\\bad.md",
        "\\\\server\\share\\bad.md",
        "https://example.invalid/bad.md",
        "../bad.md",
        "daily/../bad.md",
        "..\\bad.md",
    ],
)
def test_direct_sql_rejects_unsafe_memory_note_paths(bad_path: str) -> None:
    """Given an unsafe path, When a note is inserted, Then SQLite rejects it."""
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        _insert_entity(store.connection, "entity")

        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO memory_notes "
                "(note_id, entity_id, note_type, path) VALUES (?, ?, ?, ?)",
                ("note-unsafe", "entity", "daily", bad_path),
            )


def test_accepts_relative_note_and_logical_history_evidence() -> None:
    """Given final references, When inserted, Then logical links are accepted."""
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        _insert_entity(store.connection, "entity")
        store.connection.execute(
            "INSERT INTO memory_notes "
            "(note_id, entity_id, note_type, path, meta_json) VALUES (?, ?, ?, ?, ?)",
            ("note-1", "entity", "daily", "daily/2026-07-30.md", "{}"),
        )
        store.connection.execute(
            "INSERT INTO source_evidence_links "
            "(link_id, target_type, target_id, source_db, source_type, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("link-1", "note", "note-1", "history", "message", "msg-1"),
        )

        row = store.connection.execute(
            "SELECT source_id FROM source_evidence_links WHERE link_id = ?",
            ("link-1",),
        ).fetchone()

    assert row["source_id"] == "msg-1"


def test_direct_sql_rejects_invalid_evidence_source_and_note_json() -> None:
    """Given final source rules, When invalid values are inserted, Then writes fail."""
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        _insert_entity(store.connection, "entity")
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO memory_notes "
                "(note_id, entity_id, note_type, path, meta_json) "
                "VALUES (?, ?, ?, ?, ?)",
                ("note-1", "entity", "daily", "daily/note.md", "not-json"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO source_evidence_links "
                "(link_id, target_type, target_id, source_db, source_type, source_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("link-1", "entity", "entity", "history", "attachment", "att-1"),
            )


def test_has_sensory_indexes_without_a_tenth_table() -> None:
    """Given final schema, When inspected, Then sensory access uses indexes only."""
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        indexes = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        tables = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "sensory_index" not in tables
    assert "idx_entities_sensory_lookup" in indexes
    assert "idx_entity_edges_sensory_relation" in indexes
