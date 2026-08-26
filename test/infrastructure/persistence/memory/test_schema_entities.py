"""Target Memory fact tables and node constraints."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import pytest

from elfie.brain.memory.memory_records import NodeInput
from infrastructure.persistence.memory import (
    MemoryStorePathError,
    SQLiteMemoryStoreAdapter,
)
from infrastructure.persistence.memory.schema import KNOWLEDGE_TABLES

EXPECTED_TABLES = set(KNOWLEDGE_TABLES) | {"episodes_fts", "nodes_fts"}


def test_creates_target_tables_and_private_database(tmp_path: Path) -> None:
    db_path = tmp_path / "memory" / "knowledge.sqlite"
    db_path.parent.mkdir()

    with SQLiteMemoryStoreAdapter(db_path) as store:
        tables = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert tables == EXPECTED_TABLES
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


def test_schema_initialization_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(db_path):
        pass
    with SQLiteMemoryStoreAdapter(db_path) as store:
        tables = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert store.schema_version == 2

    assert tables == EXPECTED_TABLES


def test_rejects_non_final_filename_and_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real.sqlite"
    target.touch()
    link = tmp_path / "knowledge.sqlite"
    link.symlink_to(target)

    with pytest.raises(MemoryStorePathError):
        SQLiteMemoryStoreAdapter(tmp_path / "graph_memory.db")
    with pytest.raises(MemoryStorePathError):
        SQLiteMemoryStoreAdapter(link)


def test_nodes_keep_metadata_but_not_hidden_graph_edges() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.upsert_node_record(
            NodeInput(
                node_id="owner",
                node_type="person",
                canonical_label="主人",
                properties={"relationship_label": "owner"},
            )
        )
        row = store.connection.execute(
            "SELECT properties_json FROM nodes WHERE node_id='owner'"
        ).fetchone()
        assert "edges" not in row[0]
        assert store.get_node("owner").content == "主人"


def test_direct_sql_enforces_json_scores_and_foreign_keys() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO nodes(node_id,node_type,canonical_label,normalized_label,properties_json,updated_at)"
                " VALUES ('bad','person','坏','坏','not-json','now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO nodes(node_id,node_type,canonical_label,normalized_label,confidence,updated_at)"
                " VALUES ('bad-score','person','坏','坏',1.2,'now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                "INSERT INTO node_aliases(alias_id,node_id,alias,normalized_alias,created_at)"
                " VALUES ('a','missing','别名','别名','now')"
            )


def test_assertions_require_one_object_form_and_preserve_duplicate_claims() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.upsert_node_record(NodeInput("a", "person", "甲"))
        store.upsert_node_record(NodeInput("b", "person", "乙"))
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """INSERT INTO assertions(
                    assertion_id,subject_node_id,predicate,object_node_id,
                    object_literal_json,fingerprint,created_at,updated_at
                ) VALUES ('bad','a','knows','b','{}','bad','now','now')"""
            )
