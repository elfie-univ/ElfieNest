"""Persisted self-model projections read the existing Elfie graph only."""

from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    NodeInput,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def test_self_model_graph_uses_existing_anchor_and_does_not_expand_recursively() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="slice-test") as store:
        store.record_episode(
            ClosedEpisode("source", "source-key", "2026-09-25", "初始化资料")
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="source",
                nodes=(
                    NodeInput(
                        "genesis:self:slice-test",
                        "elfie",
                        "测试精灵",
                        properties={"elfie_id": "slice-test", "is_self": True},
                    ),
                    NodeInput("claim", "claim", "一个命题"),
                    NodeInput("concept", "concept", "相关概念"),
                ),
                assertions=(
                    AssertionInput(
                        "genesis:self:slice-test",
                        "believes",
                        object_node_id="claim",
                        evidence_ids=("evidence-source",),
                    ),
                    AssertionInput(
                        "claim",
                        "implies",
                        object_node_id="concept",
                        evidence_ids=("evidence-source",),
                    ),
                ),
                evidence=(
                    EvidenceInput(
                        "evidence-source",
                        "episode",
                        "source",
                        excerpt="初始化资料",
                    ),
                ),
                ontology_revision=store.ontology.revision,
            )
        )

        snapshot = store.get_self_model_graph(store.ontology.self_stance_predicates)

    assert {node.node_id for node in snapshot.nodes} == {
        "genesis:self:slice-test",
        "claim",
    }
    assert {assertion.predicate for assertion in snapshot.assertions} == {"believes"}
