"""Source-grounded pairwise relationship extraction tests."""

from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    ConsolidationProjection,
    ConsolidationRequest,
    EvidenceInput,
    NodeInput,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


class _EmptyMemoryProposal:
    """Keep this test on the deterministic fallback without a provider."""

    def ask_with_food(self, **_kwargs: object) -> str:
        return '{"nodes":[],"mentions":[],"assertions":[]}'


class _ReverseFriendProposal:
    """Model fixture that repeats both directions of one symmetric fact."""

    def ask_with_food(self, **_kwargs: object) -> str:
        return (
            '{"nodes":[{"label":"Ari","type":"elfie"},'
            '{"label":"Ena","type":"elfie"}],"mentions":[],'
            '"assertions":['
            '{"subject_ref":"Ari","predicate":"friend_of","object_ref":"Ena"},'
            '{"subject_ref":"Ena","predicate":"friend_of","object_ref":"Ari"}'
            "]}"
        )


def test_explicit_pairwise_relationships_are_sourced_between_elfies() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="relationship-test") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="relationship-episode",
                idempotency_key="relationship-episode",
                occurred_from="2026-09-23T00:00:00+00:00",
                content_text="Nemi 和 Pela 是朋友。Nemi 和 Savi 是家人。",
                importance=0.9,
                retention_profile="salient",
            )
        )

        receipt = MemoryConsolidator(store, elfie_id="relationship-test").run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_EmptyMemoryProposal(),
        )

        assert receipt.status == "completed"
        nodes = {node.label: node for node in store.list_graph_nodes(limit=100)}
        assert nodes["Nemi"].node_type == "elfie"
        assert nodes["Pela"].node_type == "elfie"
        assert nodes["Savi"].node_type == "elfie"
        assert "朋友" not in nodes
        assert not any(node.node_type == "event" for node in nodes.values())

        assertions = store.list_graph_assertions(limit=100)
        nodes_by_id = {node.node_id: node for node in nodes.values()}
        relation_rows = {
            (
                nodes_by_id[assertion.subject_id].label,
                assertion.predicate,
                nodes_by_id[assertion.object_node_id].label,
            )
            for assertion in assertions
            if assertion.object_node_id is not None
            and assertion.predicate in {"friend_of", "kin_of"}
            and assertion.subject_id in nodes_by_id
            and assertion.object_node_id in nodes_by_id
        }
        assert ("Nemi", "friend_of", "Pela") in relation_rows or (
            "Pela",
            "friend_of",
            "Nemi",
        ) in relation_rows
        assert ("Nemi", "kin_of", "Savi") in relation_rows or (
            "Savi",
            "kin_of",
            "Nemi",
        ) in relation_rows
        assert (
            len(
                [
                    assertion
                    for assertion in assertions
                    if assertion.predicate == "friend_of"
                ]
            )
            == 1
        )
        assert (
            len(
                [
                    assertion
                    for assertion in assertions
                    if assertion.predicate == "kin_of"
                ]
            )
            == 1
        )
        assert not any(
            assertion.predicate in {"about", "knows", "knows_boundary", "related_to"}
            for assertion in assertions
        )
        assert all(
            assertion.evidence_ids
            for assertion in assertions
            if assertion.predicate in {"friend_of", "kin_of"}
        )


def test_model_reverse_symmetric_proposals_are_canonicalized_and_weighted() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="model-relation-test") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="model-relation-episode",
                idempotency_key="model-relation-episode",
                occurred_from="2026-09-23T00:00:00+00:00",
                content_text="Ari 和 Ena 是朋友。",
                importance=0.9,
                retention_profile="salient",
            )
        )

        receipt = MemoryConsolidator(store, elfie_id="model-relation-test").run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_ReverseFriendProposal(),
        )

        assert receipt.status == "completed"
        friends = [
            assertion
            for assertion in store.list_graph_assertions(limit=100)
            if assertion.predicate == "friend_of"
        ]
        assert len(friends) == 1
        assert friends[0].importance == 0.82
        assert friends[0].subject_id < friends[0].object_node_id


def test_cooccurrence_does_not_infer_a_social_relationship() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="cooccurrence-test") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="cooccurrence-episode",
                idempotency_key="cooccurrence-episode",
                occurred_from="2026-09-23T00:00:00+00:00",
                content_text="Nemi 和 Pela 在花园一起玩。",
            )
        )

        MemoryConsolidator(store, elfie_id="cooccurrence-test").run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_EmptyMemoryProposal(),
        )

        assert not [
            assertion
            for assertion in store.list_graph_assertions(limit=100)
            if assertion.predicate in {"friend_of", "kin_of"}
        ]


def test_pairwise_relationship_reuses_the_genesis_elfie_scope() -> None:
    elfie_id = "scope-test"
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id=elfie_id) as store:
        store.record_episode(
            ClosedEpisode(
                "genesis-episode", "genesis-episode", "2026-09-23", "初始关系"
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="genesis-episode",
                nodes=(
                    NodeInput(
                        "genesis:nemi",
                        "elfie",
                        "Nemi",
                        scope=f"elfie:{elfie_id}",
                        properties={"elfie_id": elfie_id, "is_self": False},
                    ),
                    NodeInput(
                        "genesis:pela",
                        "elfie",
                        "Pela",
                        scope=f"elfie:{elfie_id}",
                        properties={"elfie_id": elfie_id, "is_self": False},
                    ),
                ),
                evidence=(
                    EvidenceInput(
                        "genesis-evidence",
                        "episode",
                        "genesis-episode",
                        excerpt="初始关系",
                    ),
                ),
            )
        )
        store.record_episode(
            ClosedEpisode(
                "scoped-relationship",
                "scoped-relationship",
                "2026-09-23",
                "Nemi 和 Pela 是朋友。",
            )
        )

        receipt = MemoryConsolidator(store, elfie_id=elfie_id).run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_EmptyMemoryProposal(),
        )

        assert receipt.status == "completed"
        nodes = store.list_graph_nodes(limit=100)
        nemi_nodes = [node for node in nodes if node.label == "Nemi"]
        pela_nodes = [node for node in nodes if node.label == "Pela"]
        assert [node.node_id for node in nemi_nodes] == ["genesis:nemi"]
        assert [node.node_id for node in pela_nodes] == ["genesis:pela"]
        assert any(
            assertion.predicate == "friend_of"
            and {
                assertion.subject_id,
                assertion.object_node_id,
            }
            == {"genesis:nemi", "genesis:pela"}
            for assertion in store.list_graph_assertions(limit=100)
        )


def test_pairwise_relation_specificity_and_importance_are_sourced() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="relation-salience-test") as store:
        store.record_episode(
            ClosedEpisode(
                "relation-salience-episode",
                "relation-salience-episode",
                "2026-09-23",
                "Nemi 和 Pela 是青梅竹马。Nemi 和 Tovren 是邻居。",
            )
        )
        MemoryConsolidator(store, elfie_id="relation-salience-test").run_batch(
            ConsolidationRequest(max_episodes=1), model_port=_EmptyMemoryProposal()
        )
        assertions = store.list_graph_assertions(limit=100)
        by_predicate = {assertion.predicate: assertion for assertion in assertions}
        assert (
            by_predicate["friend_of"].importance
            > by_predicate["neighbor_of"].importance
        )
        assert "specificity=childhood_companion" in str(
            by_predicate["friend_of"].qualifiers.get("context")
        )


def test_explicit_parent_sentence_keeps_direction_and_reverse_role() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="directed-relation-test") as store:
        store.record_episode(
            ClosedEpisode(
                "directed-relation-episode",
                "directed-relation-episode",
                "2026-09-23",
                "Mira 是 Ari 的妈妈。",
            )
        )
        MemoryConsolidator(store, elfie_id="directed-relation-test").run_batch(
            ConsolidationRequest(max_episodes=1), model_port=_EmptyMemoryProposal()
        )
        assertions = store.list_graph_assertions(limit=100)
        parent = next(
            assertion for assertion in assertions if assertion.predicate == "parent_of"
        )
        nodes = {node.node_id: node.label for node in store.list_graph_nodes(limit=100)}
        assert nodes[parent.subject_id] == "Mira"
        assert nodes[parent.object_node_id] == "Ari"
        assert "specificity=mother" in str(parent.qualifiers.get("context"))
