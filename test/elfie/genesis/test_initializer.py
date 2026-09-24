import json
from dataclasses import replace

import pytest

from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.memory_records import ConsolidationRequest, RecallRequest
from elfie.genesis import (
    GenesisMemoryCommitter,
    GenesisValidationError,
    genesis_content_hash,
)
from elfie.genesis.serialization import safe_component
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

from .test_contracts import _bundle


class _GenesisKnowledgeProposal:
    """Deterministic night worker used to prove Episode-to-graph extraction."""

    def ask_with_food(self, **kwargs: object) -> str:
        prompt = str(kwargs.get("prompt", ""))
        if "Elfaria" in prompt and "星球" in prompt:
            return json.dumps(
                {
                    "nodes": [
                        {
                            "title": "Elfaria",
                            "label": "Elfaria",
                            "type": "knowledge",
                            "context": "Elfaria 是精灵生活的星球",
                            "reusable_knowledge": True,
                        }
                    ],
                    "mentions": [
                        {
                            "surface_text": "Elfaria",
                            "label": "Elfaria",
                            "role": "concept",
                        }
                    ],
                    "assertions": [],
                },
                ensure_ascii=False,
            )
        return '{"nodes":[],"mentions":[],"assertions":[]}'


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
        assert storage.count_episodes() == len(bundle.knowledge_seeds) + len(
            bundle.episode_seeds
        )
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
        first_relationship = bundle.relationship_seeds[0]
        relationship_target = (
            first_relationship.object_id or first_relationship.person_id
        )
        person_id = (
            f"genesis:person:genesis-check:{safe_component(relationship_target)}"
        )
        assert (
            storage.get_graph_node(person_id).properties["relationship_label"]
            == "family"
        )
        assert storage.get_graph_node(person_id).node_type == "elfie"
        assert storage.get_graph_node(person_id).properties["entity_type"] == "elfie"
        assert storage.get_graph_node(person_id).properties["object_kind"] == "elfie"
        owner_node = storage.get_graph_node(
            "genesis:person:genesis-check:owner-genesis-owner"
        )
        assert owner_node.node_type == "group"
        assert owner_node.properties["entity_type"] == "group"
        assert owner_node.properties["object_kind"] == "group"
        human_owner = storage.get_graph_node(
            "genesis:person:genesis-check:owner-person-genesis-owner"
        )
        assert human_owner.node_type == "person"
        assert human_owner.properties["entity_type"] == "person"
        assert human_owner.properties["object_kind"] == "person"
        assert human_owner.properties["is_owner"] is True
        assert all(
            row["role"] == row["node_type"]
            for row in storage.conn.execute(
                """SELECT m.role, n.node_type
                     FROM episode_mentions AS m
                     JOIN nodes AS n ON n.node_id = m.node_id
                    WHERE m.resolution_state='resolved'"""
            )
        )
        assert storage.get_graph_node(person_id).importance == pytest.approx(0.37)
        assert storage.conn.execute(
            """SELECT importance FROM assertions
                WHERE subject_node_id='genesis:self:genesis-check'
                  AND predicate='kin_of'
                  AND object_node_id=?""",
            (person_id,),
        ).fetchone()[0] == pytest.approx(0.37)
        assert any(
            assertion.predicate == "kin_of"
            for assertion in storage.list_graph_assertions(limit=100)
            if assertion.subject_id == "genesis:self:genesis-check"
        )
        place_edges = [
            assertion
            for assertion in storage.list_graph_assertions(limit=5000)
            if assertion.predicate == "located_in"
        ]
        assert place_edges
        mistyville = "genesis:place:genesis-check:mistyville"
        elfaria = "genesis:place:genesis-check:elfaria"
        assert any(
            assertion.subject_id == mistyville and assertion.object_node_id == elfaria
            for assertion in place_edges
        )
        assert all(assertion.evidence_ids for assertion in place_edges)
        for kind in ("elfie", "person", "group"):
            expected = sum(
                relationship.object_kind == kind
                for relationship in bundle.relationship_seeds
            ) + (kind == "elfie")
            assert (
                storage.conn.execute(
                    "SELECT COUNT(*) FROM nodes "
                    "WHERE json_extract(properties_json, '$.entity_type')=?",
                    (kind,),
                ).fetchone()[0]
                == expected
            )
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM nodes "
            "WHERE json_extract(properties_json, '$.entity_type')='place'"
        ).fetchone()[0] == len(bundle.place_seeds)
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE episode_id LIKE 'genesis:episode:%'"
        ).fetchone()[0] == len(bundle.knowledge_seeds) + len(bundle.episode_seeds)
        assert not storage.list_graph_nodes(limit=1000, privacy_scope=None) or not any(
            node.node_type == "event" for node in storage.list_graph_nodes(limit=1000)
        )


def test_genesis_keeps_knowledge_as_source_episodes_until_nightly_consolidation() -> (
    None
):
    bundle = _bundle()
    elfaria_source = next(
        seed
        for seed in bundle.knowledge_seeds
        if "Elfaria 是精灵生活的星球" in seed.content
    )
    elfaria_episode_id = (
        "genesis:episode:genesis-check:knowledge:"
        f"{safe_component(elfaria_source.seed_id)}"
    )

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        GenesisMemoryCommitter().commit(bundle, storage)

        for seed in bundle.knowledge_seeds:
            episode = storage.get_episode(
                "genesis:episode:genesis-check:knowledge:"
                f"{safe_component(seed.seed_id)}"
            )
            assert episode is not None
            assert episode.content_text == seed.content
            assert episode.metadata["knowledge_id"] == seed.seed_id
            assert episode.metadata["topic"] == seed.topic
        assert not [
            node
            for node in storage.list_graph_nodes(limit=1000)
            if node.node_type == "knowledge"
        ]
        assert not [
            node
            for node in storage.list_graph_nodes(limit=1000)
            if node.node_type == "event"
        ]
        assert not any(
            assertion.predicate in {"knows", "knows_boundary"}
            for assertion in storage.list_graph_assertions(limit=5000)
        )

        source_recall = storage.recall(
            RecallRequest(text="Elfaria 是精灵生活的星球", lexical_limit=10)
        )
        assert any(
            item.episode_id == elfaria_episode_id for item in source_recall.episodes
        )
        assert "genesis:self-model:genesis-check" not in {
            node.node_id for node in source_recall.focus_nodes
        }

        batch = MemoryConsolidator(storage, elfie_id="genesis-check").run_batch(
            ConsolidationRequest(max_episodes=200),
            model_port=_GenesisKnowledgeProposal(),
        )
        assert len(batch.consolidated_episode_ids) == len(bundle.knowledge_seeds) + len(
            bundle.episode_seeds
        )
        elfaria = next(
            node
            for node in storage.list_graph_nodes(limit=2000)
            if node.label == "Elfaria" and node.node_type == "knowledge"
        )
        assert elfaria.node_type == "knowledge"
        assert any(
            evidence.source_id == elfaria_episode_id
            for evidence in storage.list_memory_evidence(limit=5000)
        )


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
