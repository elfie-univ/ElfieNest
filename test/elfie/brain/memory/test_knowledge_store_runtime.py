from __future__ import annotations

import sqlite3
from pathlib import Path

from elfie import ElfieFactory
from elfie.brain.memory.knowledge_schema import KNOWLEDGE_TABLES
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def _user_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def test_factory_workspace_uses_only_final_knowledge_database(tmp_path: Path) -> None:
    # Given
    workspace = tmp_path / "elfie-workspace"

    # When
    elfie = ElfieFactory().create(
        config_dir=workspace,
        elfie_id="elfie-runtime",
        profile_store=YamlProfileStoreAdapter(workspace / "profile"),
    )

    # Then
    db_path = workspace / "memory" / "knowledge.sqlite"
    assert db_path.is_file()
    assert _user_tables(db_path) == set(KNOWLEDGE_TABLES)
    assert not list(workspace.rglob("graph_memory.db"))
    elfie.memory.close()


def test_record_reopen_retrieve_and_consolidate_uses_final_store(
    tmp_path: Path,
) -> None:
    # Given
    workspace = tmp_path / "elfie-workspace"
    first = ElfieFactory().create(
        config_dir=workspace,
        elfie_id="elfie-runtime",
        profile_store=YamlProfileStoreAdapter(workspace / "profile"),
    )
    first.memory.record_episode(
        content="今天在花园看到了金色的花",
        emotion="happy",
        intensity=80.0,
    )
    first.memory.close()

    # When
    reopened = ElfieFactory().create(
        config_dir=workspace,
        elfie_id="elfie-runtime",
        profile_store=YamlProfileStoreAdapter(workspace / "profile"),
    )
    memories = reopened.memory.retrieve_relevant_memories("金色的花")
    result = reopened.memory.run_consolidation()

    # Then
    assert "今天在花园看到了金色的花" in memories
    assert result["consolidated_count"] == 1
    assert not list(workspace.rglob("graph_memory.db"))
    reopened.memory.close()


def test_product_memory_modules_do_not_reference_legacy_graph_store() -> None:
    # Given
    memory_dir = Path(__file__).parents[4] / "elfie" / "brain" / "memory"
    product_modules = (
        "memory_system.py",
        "encoding.py",
        "retrieval.py",
        "spreading_activation.py",
        "core_cognition.py",
        "consolidation.py",
        "sensory_index.py",
        "context_assembly.py",
    )

    # When
    sources = {
        name: (memory_dir / name).read_text(encoding="utf-8")
        for name in product_modules
    }

    # Then
    for name, source in sources.items():
        assert "GraphStorage" not in source, name
        assert "graph_memory.db" not in source, name
        assert "FROM nodes" not in source, name
        assert "INTO nodes" not in source, name
