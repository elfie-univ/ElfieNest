from __future__ import annotations

import sqlite3
from pathlib import Path

from elfie import ElfieFactory
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.memory.schema import KNOWLEDGE_TABLES
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def _user_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def test_factory_workspace_uses_only_final_knowledge_database(tmp_path: Path) -> None:
    workspace = tmp_path / "elfie-workspace"
    profile = _profile(workspace)
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter(
                workspace / "memory" / "knowledge.sqlite"
            ),
        )
    )

    db_path = workspace / "memory" / "knowledge.sqlite"
    assert db_path.is_file()
    assert _user_tables(db_path) == set(KNOWLEDGE_TABLES)
    assert not list(workspace.rglob("graph_memory.db"))
    ElfieDiagnostics(elfie).memory.storage.close()


def test_record_reopen_retrieve_and_consolidate_uses_final_store(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "elfie-workspace"
    profile = _profile(workspace)
    first = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter(
                workspace / "memory" / "knowledge.sqlite"
            ),
        )
    )
    ElfieDiagnostics(first).memory.record_episode(
        content="今天在花园看到了金色的花",
        emotion="happy",
        intensity=80.0,
    )
    ElfieDiagnostics(first).memory.storage.close()

    reopened = ElfieFactory().restore(
        ElfieAssembly(
            profile=YamlProfileStoreAdapter(workspace / "profile").load(),
            memory_store=SQLiteMemoryStoreAdapter(
                workspace / "memory" / "knowledge.sqlite"
            ),
        )
    )
    memories = ElfieDiagnostics(reopened).memory.retrieve_relevant_memories("金色的花")
    result = ElfieDiagnostics(reopened).memory.run_consolidation()

    assert "今天在花园看到了金色的花" in memories
    assert result["consolidated_count"] == 1
    assert not list(workspace.rglob("graph_memory.db"))
    ElfieDiagnostics(reopened).memory.storage.close()


def test_product_memory_modules_do_not_reference_legacy_graph_store() -> None:
    memory_dir = Path(__file__).parents[4] / "elfie" / "brain" / "memory"
    product_modules = (
        "memory_system.py",
        "encoding.py",
        "retrieval.py",
        "spreading_activation.py",
        "self_narrative.py",
        "consolidation.py",
        "sensory_index.py",
    )
    sources = {
        name: (memory_dir / name).read_text(encoding="utf-8")
        for name in product_modules
    }

    for name, source in sources.items():
        assert "GraphStorage" not in source, name
        assert "graph_memory.db" not in source, name
        assert "FROM nodes" not in source, name
        assert "INTO nodes" not in source, name


def _profile(workspace: Path):
    workspace.mkdir(parents=True, exist_ok=True)
    profile_store = YamlProfileStoreAdapter(workspace / "profile")
    profile = profile_store.load() if profile_store.exists() else None
    if profile is None:
        from elfie.initialization import assemble_profile

        profile = assemble_profile(elfie_id="elfie-runtime", supplied=None)
        profile_store.save(profile)
    (workspace / "memory").mkdir(parents=True, exist_ok=True)
    return profile
