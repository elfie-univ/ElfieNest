from __future__ import annotations

import sqlite3
from pathlib import Path

from app.infrastructure.persistence.elfie_cognition_reader import (
    read_elfie_cognition,
)
from elfie.brain.memory.knowledge_store import KnowledgeStore
from elfie.brain.memory.node_types import MemoryNode


def test_missing_and_empty_knowledge_stores_are_empty_without_creation(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing" / "knowledge.sqlite"

    missing_result = read_elfie_cognition(missing)

    assert missing_result.status == "empty"
    assert not missing.exists()

    empty = tmp_path / "empty" / "knowledge.sqlite"
    empty.parent.mkdir()
    with sqlite3.connect(empty):
        pass

    before = empty.stat()
    empty_result = read_elfie_cognition(empty)
    after = empty.stat()

    assert empty_result.status == "empty"
    assert (before.st_size, before.st_mtime_ns) == (
        after.st_size,
        after.st_mtime_ns,
    )


def test_reader_returns_structured_final_store_rows_without_writing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    with KnowledgeStore(path) as store:
        store.add_node(
            MemoryNode(
                id="core_world",
                type="core",
                content="大多数时候世界是安全的。",
                metadata={"core_key": "world"},
            )
        )
        store.add_node(
            MemoryNode(
                id="event_adoption",
                type="episodic",
                content="被主人领养，搬进了新的家。",
                metadata={
                    "timestamp": "2026-06-30T08:00:00Z",
                    "major_event": True,
                    "importance": 0.95,
                    "title": "被领养",
                    "changed": "从此有了自己的家",
                    "people": ["主人"],
                },
            )
        )

    before = path.stat()
    result = read_elfie_cognition(path)
    after = path.stat()

    assert result.status == "ready"
    assert result.snapshot is not None
    assert result.snapshot.core_world == "大多数时候世界是安全的。"
    assert result.snapshot.events[0].id == "event_adoption"
    assert (before.st_size, before.st_mtime_ns) == (
        after.st_size,
        after.st_mtime_ns,
    )


def test_locked_or_corrupt_knowledge_stores_are_unavailable(tmp_path: Path) -> None:
    locked = tmp_path / "locked" / "knowledge.sqlite"
    locked.parent.mkdir()
    with KnowledgeStore(locked):
        lock = sqlite3.connect(locked)
        try:
            lock.execute("BEGIN EXCLUSIVE")
            locked_result = read_elfie_cognition(locked)
        finally:
            lock.rollback()
            lock.close()

    corrupt = tmp_path / "corrupt" / "knowledge.sqlite"
    corrupt.parent.mkdir()
    corrupt.write_bytes(b"not a sqlite database")

    assert locked_result.status == "unavailable"
    assert read_elfie_cognition(corrupt).status == "unavailable"


def test_reader_keeps_node_importance_and_relationship_closeness_separate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    with KnowledgeStore(path) as store:
        store.add_node(
            MemoryNode(
                id="person-owner",
                type="entity",
                content="主人",
                metadata={
                    "entity_type": "person",
                    "relationship": "主人",
                    "relation_kind": "owner",
                    "importance": 0.95,
                },
            )
        )
        store.connection.execute(
            "UPDATE people SET closeness_score = ?, importance_score = ? WHERE entity_id = ?",
            (0.22, 0.7, "person-owner"),
        )
        store.connection.commit()

    result = read_elfie_cognition(path)

    assert result.snapshot is not None
    owner = result.snapshot.entities[0]
    assert owner.weight == 0.95
    assert owner.closeness == 0.22
