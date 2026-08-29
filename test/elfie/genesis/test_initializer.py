from dataclasses import replace

import pytest

from elfie.brain.memory.retrieval import MemoryRetriever
from elfie.genesis import GenesisMemoryCommitter, GenesisValidationError
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

from .test_contracts import _bundle


def test_genesis_commit_materializes_memory_entities_and_is_idempotent() -> None:
    bundle = _bundle()
    bundle = replace(
        bundle,
        relationship_seeds=(replace(bundle.relationship_seeds[0], importance=0.37),),
    )
    committer = GenesisMemoryCommitter()

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        first = committer.commit(bundle, storage)
        second = committer.commit(bundle, storage)

        assert first.status == "committed"
        assert second.status == "duplicate"
        assert storage.count_nodes("episodic") == 2
        assert (
            storage.get_node("genesis:memory:m-0").metadata["emotion_intensity"] == 0.5
        )
        assert (
            storage.get_node("genesis:self:genesis-check").metadata["is_self"] is True
        )
        assert (
            storage.get_node("genesis:person:seli").metadata["relationship_label"]
            == "mother"
        )
        assert storage.get_node("genesis:person:seli").metadata["importance"] == (
            pytest.approx(0.37)
        )
        assert storage.conn.execute(
            """SELECT importance FROM assertions
                WHERE subject_node_id='genesis:self:genesis-check'
                  AND predicate='relationship'
                  AND object_node_id='genesis:person:seli'"""
        ).fetchone()[0] == pytest.approx(0.37)
        assert any(
            edge.rel == "relationship"
            for edge in storage.get_edges("genesis:self:genesis-check")
        )
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE json_extract(properties_json, '$.entity_type')='elfie'"
            ).fetchone()[0]
            == 1
        )
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE json_extract(properties_json, '$.entity_type')='person'"
            ).fetchone()[0]
            == 1
        )
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE json_extract(properties_json, '$.entity_type')='place'"
            ).fetchone()[0]
            == 3
        )
        # Target storage keeps each Genesis story as one source Episode.  It
        # must not create a compatibility node with the same identifier or
        # lose the Episode evidence chain during initialization.
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE node_id='genesis:memory:m-0'"
            ).fetchone()[0]
            == 0
        )
        assert (
            storage.conn.execute(
                "SELECT consolidation_state FROM episodes WHERE episode_id='genesis:memory:m-0'"
            ).fetchone()[0]
            == "consolidated"
        )
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE source_type='episode' AND source_id='genesis:memory:m-0'"
            ).fetchone()[0]
            == 1
        )


def test_genesis_materializes_each_known_fact_as_recallable_knowledge() -> None:
    bundle = _bundle()

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        GenesisMemoryCommitter().commit(bundle, storage)

        fact_nodes = [
            node
            for node in storage.get_nodes_by_type("knowledge", limit=100)
            if node.metadata.get("genesis_kind") == "knowledge_fact"
        ]

        assert [node.content for node in fact_nodes] == list(
            bundle.self_model_seed.known_facts
        )
        assert all(node.metadata.get("recall_eligible") is True for node in fact_nodes)
        assert all(node.metadata.get("source_event_ids") for node in fact_nodes)
        assert all(node.metadata.get("certainty") == "high" for node in fact_nodes)

        recalled_ids = {
            node.id
            for node in MemoryRetriever(storage).retrieve_by_text(
                "来自 Elfaria", top_k=10
            )
        }
        assert "genesis:knowledge:genesis-check:0" in recalled_ids
        assert "genesis:self-model:genesis-check" not in recalled_ids


def test_genesis_rejects_a_second_manifest_for_the_same_elfie() -> None:
    bundle = _bundle()
    conflicting = replace(
        bundle,
        manifest=replace(bundle.manifest, manifest_id="different-manifest"),
    )

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        committer = GenesisMemoryCommitter()
        committer.commit(bundle, storage)
        with pytest.raises(GenesisValidationError, match="另一个 Genesis manifest"):
            committer.commit(conflicting, storage)
