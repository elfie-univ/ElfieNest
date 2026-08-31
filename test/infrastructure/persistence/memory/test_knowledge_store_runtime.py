from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from elfie import ElfieFactory
from elfie.brain.memory.memory_records import ClosedEpisode, RecallRequest
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.memory.schema import KNOWLEDGE_TABLES
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


class _GroundedMemoryModel:
    def ask_with_food(self, **_: object) -> str:
        return json.dumps(
            {
                "nodes": [
                    {
                        "label": "花园",
                        "type": "place",
                        "description": "花园",
                    }
                ],
                "mentions": [
                    {"surface_text": "花园", "label": "花园", "role": "place"}
                ],
                "assertions": [],
            },
            ensure_ascii=False,
        )


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
    assert _user_tables(db_path) == set(KNOWLEDGE_TABLES) | {
        "episodes_fts",
        "nodes_fts",
    }
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
    ElfieDiagnostics(first).memory.record_closed_episode(
        ClosedEpisode(
            episode_id="garden-episode",
            idempotency_key="garden-key",
            occurred_from="2026-08-01T00:00:00+00:00",
            content_text="今天在花园看到了金色的花",
            emotion="happy",
            importance=0.8,
        )
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
    memories = ElfieDiagnostics(reopened).memory.recall(
        RecallRequest(text="金色的花", episode_limit=5)
    )
    result = ElfieDiagnostics(reopened).memory.run_consolidation(
        model_port=_GroundedMemoryModel()
    )

    assert memories.episodes[0].episode_id == "garden-episode"
    assert result["consolidated_count"] == 1
    assert not list(workspace.rglob("graph_memory.db"))
    ElfieDiagnostics(reopened).memory.storage.close()


def test_encoded_entity_edge_retrieves_episode_from_sqlite(tmp_path: Path) -> None:
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
    memory = ElfieDiagnostics(elfie).memory

    receipt = memory.record_closed_episode(
        ClosedEpisode(
            episode_id="blue-episode",
            idempotency_key="blue-key",
            occurred_from="2026-08-01T00:00:00+00:00",
            content_text="主人说他喜欢蓝色。",
            emotion="attachment",
            importance=0.6,
            stimulus="completed-owner-interaction",
        )
    )
    bundle = memory.recall(
        RecallRequest(text="主人", mode="basic_local", episode_limit=5)
    )

    assert receipt.episode_id
    assert [item.episode_id for item in bundle.episodes] == [receipt.episode_id]
    memory.storage.close()


def test_product_memory_modules_do_not_reference_legacy_graph_store() -> None:
    memory_dir = Path(__file__).parents[4] / "elfie" / "brain" / "memory"
    legacy_modules = (
        "encoding.py",
        "retrieval.py",
        "spreading_activation.py",
        "emotion_weighting.py",
        "ebbinghaus_decay.py",
        "sensory_buffer.py",
        "sensory_index.py",
        "self_narrative.py",
        "recall_formatter.py",
    )
    assert all(not (memory_dir / name).exists() for name in legacy_modules)
    product_modules = ("memory_system.py", "consolidation.py", "memory_store.py")
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
