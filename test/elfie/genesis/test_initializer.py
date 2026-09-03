from dataclasses import replace

import pytest

from elfie.brain.memory.memory_records import RecallRequest
from elfie.genesis import (
    GenesisMemoryCommitter,
    GenesisValidationError,
    genesis_content_hash,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

from .test_contracts import _bundle


def test_genesis_commit_materializes_memory_entities_and_is_idempotent() -> None:
    bundle = _bundle()
    bundle = replace(
        bundle,
        relationship_seeds=(
            replace(bundle.relationship_seeds[0], importance=0.37),
            *bundle.relationship_seeds[1:],
        ),
    )
    bundle = replace(
        bundle,
        manifest=replace(
            bundle.manifest,
            content_hash=genesis_content_hash(bundle),
        ),
    )
    committer = GenesisMemoryCommitter()

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        first = committer.commit(bundle, storage)
        second = committer.commit(bundle, storage)

        assert first.status == "committed"
        assert second.status == "duplicate"
        assert storage.count_episodes() == 5
        assert (
            storage.get_episode(
                "genesis:episode:genesis-check:early-home"
            ).emotion_intensity
            == 0.8
        )
        assert (
            storage.get_graph_node("genesis:self:genesis-check").properties["is_self"]
            is True
        )
        person_id = "genesis:person:genesis-check:kin-01"
        assert (
            storage.get_graph_node(person_id).properties["relationship_label"]
            == "family"
        )
        assert storage.get_graph_node(person_id).importance == pytest.approx(0.37)
        assert storage.conn.execute(
            """SELECT importance FROM assertions
                WHERE subject_node_id='genesis:self:genesis-check'
                  AND predicate='relationship'
                  AND object_node_id=?""",
            (person_id,),
        ).fetchone()[0] == pytest.approx(0.37)
        assert any(
            assertion.predicate == "relationship"
            for assertion in storage.list_graph_assertions(limit=100)
            if assertion.subject_id == "genesis:self:genesis-check"
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
            == 13
        )
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE json_extract(properties_json, '$.entity_type')='place'"
            ).fetchone()[0]
            == 9
        )
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE episode_id LIKE 'genesis:episode:%'"
            ).fetchone()[0]
            == 5
        )


def test_genesis_materializes_each_selected_fact_as_recallable_knowledge() -> None:
    bundle = _bundle()

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        GenesisMemoryCommitter().commit(bundle, storage)

        fact_nodes = [
            node
            for node in storage.list_graph_nodes(limit=1000)
            if node.node_type == "knowledge"
        ]

        assert {node.properties["knowledge_id"] for node in fact_nodes} == {
            seed.seed_id for seed in bundle.knowledge_seeds
        }
        assert all(
            node.properties.get("recall_eligible") is True for node in fact_nodes
        )
        assert all(node.properties.get("source_ref") for node in fact_nodes)

        recalled_ids = {
            node.node_id
            for node in storage.recall(
                RecallRequest(text="母星 Elfaria", lexical_limit=10)
            ).focus_nodes
        }
        assert "genesis:knowledge:genesis-check:world-identity" in recalled_ids
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
