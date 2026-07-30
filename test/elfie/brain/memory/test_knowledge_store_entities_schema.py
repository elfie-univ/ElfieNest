"""KnowledgeStore entity-detail schema tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from elfie.brain.memory.knowledge_store import KnowledgeStore


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def _insert_entity(
    connection: sqlite3.Connection,
    entity_id: str,
    entity_type: str,
    name: str = "name",
) -> None:
    connection.execute(
        "INSERT INTO entities (entity_id, entity_type, name) VALUES (?, ?, ?)",
        (entity_id, entity_type, name),
    )


def test_card12_creates_exact_entity_detail_tables(tmp_path: Path) -> None:
    """Given explicit knowledge path, When opened, Then Card 12 tables exist."""
    db_path = tmp_path / "knowledge.sqlite"

    store = KnowledgeStore(str(db_path))
    try:
        tables = {
            row["name"]
            for row in store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        assert tables == {
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
        assert _columns(store.conn, "entities") == [
            "entity_id",
            "entity_type",
            "name",
            "aliases_json",
            "summary",
            "confidence",
            "first_seen_at",
            "last_seen_at",
            "updated_at",
            "meta_json",
        ]
        assert _columns(store.conn, "people") == [
            "entity_id",
            "display_name",
            "relationship_label",
            "closeness_score",
            "trust_score",
            "importance_score",
            "is_owner",
            "profile_summary",
            "preferences_json",
            "updated_at",
        ]
        assert _columns(store.conn, "known_elfies") == [
            "entity_id",
            "elfie_id",
            "display_name",
            "species",
            "is_self",
            "relationship_label",
            "closeness_score",
            "profile_summary",
            "updated_at",
        ]
    finally:
        store.close()


def test_card12_rejects_invalid_json_type_and_scores() -> None:
    """Given Card 12 schema, When invalid values are inserted, Then they fail."""
    store = KnowledgeStore(":memory:")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entities "
                "(entity_id, entity_type, name, aliases_json) VALUES (?, ?, ?, ?)",
                ("bad-json", "person", "Owner", "not-json"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_entity(store.conn, "bad-type", "animal")

        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entities "
                "(entity_id, entity_type, name, confidence) VALUES (?, ?, ?, ?)",
                ("bad-score", "person", "Owner", 1.2),
            )
    finally:
        store.close()


def test_card12_rejects_null_entity_identities() -> None:
    """Given Card 12 tables, When identity columns are null, Then they fail."""
    store = KnowledgeStore(":memory:")
    try:
        _insert_entity(store.conn, "person", "person", "Person")
        _insert_entity(store.conn, "elfie", "elfie", "Elfie")
        _insert_entity(store.conn, "concept", "concept", "Concept")
        _insert_entity(store.conn, "place", "place", "Place")
        _insert_entity(store.conn, "event", "event", "Event")

        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO entities (entity_id, entity_type, name) "
                "VALUES (?, ?, ?)",
                (None, "person", "Null Entity"),
            )

        detail_statements = [
            "INSERT INTO people (entity_id, display_name) VALUES (?, ?)",
            "INSERT INTO known_elfies (entity_id, display_name) VALUES (?, ?)",
            "INSERT INTO concepts (entity_id, concept_type) VALUES (?, ?)",
            "INSERT INTO places (entity_id, place_type) VALUES (?, ?)",
            "INSERT INTO events (entity_id, event_type) VALUES (?, ?)",
        ]
        for statement in detail_statements:
            with pytest.raises(sqlite3.IntegrityError):
                store.conn.execute(statement, (None, "null"))
    finally:
        store.close()


def test_card12_enforces_detail_fk_owner_self_and_known_elfie_id() -> None:
    """Given detail rows, When constraints are violated, Then SQLite rejects them."""
    store = KnowledgeStore(":memory:")
    try:
        _insert_entity(store.conn, "owner-1", "person", "Owner")
        _insert_entity(store.conn, "owner-2", "person", "Second Owner")
        _insert_entity(store.conn, "self-1", "elfie", "Self")
        _insert_entity(store.conn, "self-2", "elfie", "Other Self")
        _insert_entity(store.conn, "unknown-elfie-1", "elfie", "Unknown Elfie")
        _insert_entity(store.conn, "unknown-elfie-2", "elfie", "Unknown Elfie Two")
        _insert_entity(store.conn, "duplicate-known-id", "elfie", "Duplicate Known ID")

        store.conn.execute(
            "INSERT INTO people (entity_id, display_name, is_owner) "
            "VALUES (?, ?, ?)",
            ("owner-1", "Owner", 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO people (entity_id, display_name, is_owner) "
                "VALUES (?, ?, ?)",
                ("owner-2", "Second Owner", 1),
            )

        store.conn.execute(
            "INSERT INTO known_elfies (entity_id, elfie_id, is_self) "
            "VALUES (?, ?, ?)",
            ("self-1", "12345678", 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO known_elfies (entity_id, elfie_id, is_self) "
                "VALUES (?, ?, ?)",
                ("self-2", "87654321", 1),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO known_elfies (entity_id, elfie_id) VALUES (?, ?)",
                ("missing-entity", "11111111"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO known_elfies (entity_id, elfie_id) VALUES (?, ?)",
                ("duplicate-known-id", "12345678"),
            )
        store.conn.execute(
            "INSERT INTO known_elfies (entity_id) VALUES (?)",
            ("unknown-elfie-1",),
        )
        store.conn.execute(
            "INSERT INTO known_elfies (entity_id) VALUES (?)",
            ("unknown-elfie-2",),
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.conn.execute(
                "INSERT INTO known_elfies (entity_id, elfie_id) VALUES (?, ?)",
                ("self-2", ""),
            )
    finally:
        store.close()
