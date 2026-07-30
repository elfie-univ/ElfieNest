"""KnowledgeStore graph, note, and evidence schema tests."""

from __future__ import annotations

import sqlite3

import pytest

from elfie.brain.memory.knowledge_store import KnowledgeStore


def _insert_entity(
    connection: sqlite3.Connection,
    entity_id: str,
    entity_type: str = "concept",
) -> None:
    connection.execute(
        "INSERT INTO entities (entity_id, entity_type, name) VALUES (?, ?, ?)",
        (entity_id, entity_type, entity_id),
    )


def test_card13_creates_exact_graph_note_evidence_columns() -> None:
    """Given KnowledgeStore, When opened, Then Card 13 fields are exact."""
    store = KnowledgeStore(":memory:")
    try:
        columns = {
            table: [
                row["name"]
                for row in store.conn.execute(f"PRAGMA table_info({table})")
            ]
            for table in (
                "entity_edges",
                "memory_notes",
                "source_evidence_links",
            )
        }

        assert columns["entity_edges"] == [
            "edge_id",
            "source_entity_id",
            "target_entity_id",
            "relation_type",
            "summary",
            "weight",
            "confidence",
            "updated_at",
        ]
        assert columns["memory_notes"] == [
            "note_id",
            "entity_id",
            "note_type",
            "title",
            "path",
            "summary",
            "created_at",
            "updated_at",
            "meta_json",
        ]
        assert columns["source_evidence_links"] == [
            "link_id",
            "target_type",
            "target_id",
            "source_db",
            "source_type",
            "source_id",
            "weight",
            "created_at",
        ]
    finally:
        store.close()


def test_card13_rejects_dangling_duplicate_and_invalid_edges() -> None:
    """Given entity edges, When invalid rows are inserted, Then they fail."""
    store = KnowledgeStore(":memory:")
    try:
        _insert_entity(store.conn, "source")
        _insert_entity(store.conn, "target")
        store.conn.execute(
            "INSERT INTO entity_edges "
            "(edge_id, source_entity_id, target_entity_id, relation_type) "
            "VALUES (?, ?, ?, ?)",
            ("edge-1", "source", "target", "supports"),
        )

        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type) "
                "VALUES (?, ?, ?, ?)",
                ("edge-2", "source", "target", "supports"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type) "
                "VALUES (?, ?, ?, ?)",
                ("edge-3", "source", "missing", "supports"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type, weight) "
                "VALUES (?, ?, ?, ?, ?)",
                ("edge-4", "source", "target", "likes", -0.1),
            )
    finally:
        store.close()


def test_card13_accepts_relative_notes_and_logical_history_evidence_only() -> None:
    """Given notes and evidence, When paths/sources vary, Then only final forms pass."""
    store = KnowledgeStore(":memory:")
    try:
        _insert_entity(store.conn, "entity")
        store.conn.execute(
            "INSERT INTO memory_notes "
            "(note_id, entity_id, note_type, title, path, meta_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("note-1", "entity", "daily", "Daily", "daily/2026-07-29.md", "{}"),
        )
        store.conn.execute(
            "INSERT INTO source_evidence_links "
            "(link_id, target_type, target_id, source_db, source_type, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("link-1", "note", "note-1", "history", "message", "msg-1"),
        )
        store.conn.execute(
            "INSERT INTO source_evidence_links "
            "(link_id, target_type, target_id, source_db, source_type, source_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("link-2", "entity", "entity", "history", "conversation", "conv-1"),
        )

        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO memory_notes "
                "(note_id, entity_id, note_type, title, path) "
                "VALUES (?, ?, ?, ?, ?)",
                ("note-2", "entity", "daily", "Bad", "/tmp/bad.md"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO source_evidence_links "
                "(link_id, target_type, target_id, source_db, source_type, source_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("link-3", "note", "note-1", "history", "attachment", "att-1"),
            )
    finally:
        store.close()


def test_card13_rejects_null_graph_note_and_evidence_identities() -> None:
    """Given Card 13 tables, When identity columns are null, Then they fail."""
    store = KnowledgeStore(":memory:")
    try:
        _insert_entity(store.conn, "source")
        _insert_entity(store.conn, "target")

        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entity_edges "
                "(edge_id, source_entity_id, target_entity_id, relation_type) "
                "VALUES (?, ?, ?, ?)",
                (None, "source", "target", "supports"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO memory_notes "
                "(note_id, entity_id, note_type, title, path) "
                "VALUES (?, ?, ?, ?, ?)",
                (None, "source", "daily", "Daily", "daily/2026-07-29.md"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO source_evidence_links "
                "(link_id, target_type, target_id, source_db, source_type, source_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (None, "entity", "source", "history", "message", "msg-1"),
            )
    finally:
        store.close()


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/bad.md",
        "C:\\Users\\zhenli\\bad.md",
        "C:/Users/zhenli/bad.md",
        "\\\\server\\share\\bad.md",
        "https://example.invalid/bad.md",
        "../bad.md",
        "daily/../bad.md",
        "..\\bad.md",
        "daily\\..\\bad.md",
    ],
)
def test_card13_rejects_non_relative_memory_note_paths(bad_path: str) -> None:
    """Given unsafe note paths, When inserted, Then all are rejected."""
    store = KnowledgeStore(":memory:")
    try:
        _insert_entity(store.conn, "entity")

        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO memory_notes "
                "(note_id, entity_id, note_type, title, path) "
                "VALUES (?, ?, ?, ?, ?)",
                ("note-unsafe", "entity", "daily", "Bad", bad_path),
            )
    finally:
        store.close()


def test_card13_has_sensory_lookup_indexes_without_sensory_table() -> None:
    """Given final schema, When indexes are inspected, Then sensory lookup is indexed."""
    store = KnowledgeStore(":memory:")
    try:
        indexes = {
            row["name"]
            for row in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        tables = {
            row["name"]
            for row in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        assert "sensory_index" not in tables
        assert "idx_entities_sensory_lookup" in indexes
        assert "idx_entity_edges_sensory_relation" in indexes
    finally:
        store.close()
