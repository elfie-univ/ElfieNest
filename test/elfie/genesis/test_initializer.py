import json
from dataclasses import replace

import pytest

from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.memory_records import (
    ConsolidationRequest,
    GenesisSubmissionReceipt,
    NodeInput,
    RecallRequest,
)
from elfie.genesis import (
    GenesisMemoryCommitter,
    GenesisValidationError,
    genesis_content_hash,
)
from elfie.genesis.serialization import (
    EPISODE_NODE_PREFIX,
    SELF_NODE_PREFIX,
    safe_component,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

from .test_contracts import _bundle, _compilation


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
                            "type": "concept",
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
        source = load_genesis_source_package()

        assert first.status == "committed"
        assert second.status == "duplicate"
        assert first.node_ids == tuple(bundle.manifest.output_ids)
        assert second.node_ids == first.node_ids
        assert second.committed_at == first.committed_at
        assert storage.get_graph_node("genesis:receipt:genesis-check") is None
        submission = storage.get_genesis_submission(first.idempotency_key_digest)
        assert submission is not None
        assert submission.manifest_id == bundle.manifest.manifest_id
        assert submission.content_sha256 == bundle.manifest.content_hash
        assert len(submission.expected_ids_hash) == 64
        assert submission.committed_at
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
            == "parent"
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
                  AND predicate='child_of'
                  AND object_node_id=?""",
            (person_id,),
        ).fetchone()[0] == pytest.approx(0.37)
        assert any(
            assertion.predicate == "child_of"
            for assertion in storage.list_graph_assertions(limit=100)
            if {assertion.subject_id, assertion.object_node_id}
            == {"genesis:self:genesis-check", person_id}
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
        for place in source.places:
            if place.parent_id in {"elfaria", "earth"}:
                continue
            child_id = f"genesis:place:genesis-check:{place.place_id}"
            parent_id = f"genesis:place:genesis-check:{place.parent_id}"
            assert any(
                assertion.subject_id == child_id
                and assertion.object_node_id == parent_id
                for assertion in place_edges
            ), (place.place_id, place.parent_id)
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
        station_node = storage.get_graph_node(
            "genesis:place:genesis-check:earthbound_station"
        )
        square_node = storage.get_graph_node(
            "genesis:place:genesis-check:skyreach_square"
        )
        assert station_node is not None and square_node is not None
        assert station_node.importance > square_node.importance
        relation_assertions = {
            (assertion.predicate, assertion.subject_id, assertion.object_node_id)
            for assertion in storage.list_graph_assertions(limit=5000)
            if assertion.predicate
            in {
                "at_center_of",
                "coordinate_origin_of",
                "suspended_above",
                "outflow_from",
                "open_arc_below",
                "in_center_of",
                "public_entrance_to",
            }
        }
        assert len(relation_assertions) == len(bundle.place_relation_seeds)
        assert all(
            assertion.evidence_ids
            for assertion in storage.list_graph_assertions(limit=5000)
            if assertion.predicate
            in {
                "at_center_of",
                "coordinate_origin_of",
                "suspended_above",
                "outflow_from",
                "open_arc_below",
                "in_center_of",
                "public_entrance_to",
            }
        )
        visit_assertions = [
            assertion
            for assertion in storage.list_graph_assertions(limit=5000)
            if assertion.predicate == "visits"
            and assertion.subject_id == "genesis:self:genesis-check"
        ]
        assert visit_assertions
        assert any(
            assertion.object_node_id == "genesis:place:genesis-check:earthbound_station"
            for assertion in visit_assertions
        )
        assert all(assertion.evidence_ids for assertion in visit_assertions)
        assert not any(
            assertion.object_node_id == "genesis:place:genesis-check:skyreach_square"
            for assertion in visit_assertions
        )
        assert storage.conn.execute(
            "SELECT COUNT(*) FROM episodes WHERE episode_id LIKE 'genesis:episode:%'"
        ).fetchone()[0] == len(bundle.knowledge_seeds) + len(bundle.episode_seeds)
        route_episode = storage.get_episode(
            "genesis:episode:genesis-check:departure-decision"
        )
        assert route_episode is not None
        departure_seed = next(
            episode
            for episode in bundle.episode_seeds
            if episode.seed_id == "departure-decision"
        )
        assert route_episode.metadata["route_ids"] == list(departure_seed.route_ids)
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
            assert episode.metadata["topic_bucket"] == seed.topic
            assert seed.seed_id in episode.metadata["topic_member_ids"]
            assert episode.metadata["topic_member_count"] == len(
                episode.metadata["topic_member_ids"]
            )
        assert not [
            node
            for node in storage.list_graph_nodes(limit=1000)
            if node.node_type == "concept"
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
            if node.label == "Elfaria" and node.node_type == "concept"
        )
        assert elfaria.node_type == "concept"
        assert any(
            evidence.source_id == elfaria_episode_id
            for evidence in storage.list_memory_evidence(limit=5000)
        )


def test_genesis_commit_preserves_visit_counts_and_family_links() -> None:
    bundle = _compilation("visit-memory", seed=4, stage="mature", age_years=8).bundle
    expected_visit_ids = {
        f"genesis:episode:visit-memory:{safe_component(episode.seed_id)}"
        for episode in bundle.episode_seeds
        if episode.seed_id.startswith("visit:")
    }

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        GenesisMemoryCommitter().commit(bundle, storage)

        parent = next(
            item for item in bundle.relationship_seeds if item.role == "parent"
        )
        parent_target = parent.object_id or parent.person_id
        parent_node = storage.get_graph_node(
            f"genesis:person:visit-memory:{safe_component(parent_target)}"
        )
        assert parent_node is not None
        assert parent_node.properties["child_birth_orders"] == [
            {"person_id": person_id, "birth_order": order}
            for person_id, order in parent.child_birth_orders
        ]
        self_node = storage.get_graph_node(f"{SELF_NODE_PREFIX}visit-memory")
        assert self_node is not None
        assert (
            self_node.properties["family_birth_order"]
            == dict(parent.child_birth_orders)["self"]
        )
        assert self_node.properties["family_child_count"] == len(
            parent.child_birth_orders
        )

        visit_episodes = [
            episode
            for episode in storage.list_episodes(limit=1000)
            if episode.episode_id in expected_visit_ids
        ]
        assert visit_episodes
        metadata = visit_episodes[0].metadata
        assert metadata["visit_count"] >= 1
        assert metadata["travel_days"] >= 0
        assert metadata["stay_days"] >= 1
        assert len(metadata["visit_age_years"]) == metadata["visit_count"]
        assert metadata["purposes"]
        predicates = {
            assertion.predicate
            for assertion in storage.list_graph_assertions(limit=5000)
        }
        assert {"child_of", "kin_of"} <= predicates


def test_genesis_commit_persists_deceased_family_and_known_death_episode() -> None:
    compilation = _compilation(
        "family-death-memory",
        stage="elder",
        age_years=11,
        seed=7,
    )
    bundle = compilation.bundle
    parents = tuple(
        relationship
        for relationship in bundle.relationship_seeds
        if relationship.role == "parent"
    )
    death_episodes = tuple(
        episode
        for episode in bundle.episode_seeds
        if episode.theme_id == "family-event:death"
    )

    assert all(relationship.life_status == "deceased" for relationship in parents)
    assert {episode.person_ids[0] for episode in death_episodes} == {
        relationship.person_id for relationship in parents
    }

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        assert GenesisMemoryCommitter().commit(bundle, storage).status == "committed"

        for relationship in parents:
            target = relationship.object_id or relationship.person_id
            person_node_id = (
                f"genesis:person:family-death-memory:{safe_component(target)}"
            )
            properties = storage.get_graph_node(person_node_id).properties
            assert properties["life_status"] == "deceased"
            assert properties["death_age_years_at_genesis"] == (
                relationship.death_age_years_at_genesis
            )
            assert properties["death_event_age_years"] == (
                relationship.death_event_age_years
            )

        for episode in death_episodes:
            episode_id = (
                f"{EPISODE_NODE_PREFIX}family-death-memory:"
                f"{safe_component(episode.seed_id)}"
            )
            stored = storage.get_episode(episode_id)
            assert stored is not None
            assert stored.content_text == episode.content
            assert stored.metadata["age_years_at_event"] == episode.age_years_at_event


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


def test_genesis_rejects_a_second_idempotency_identity_for_the_same_elfie() -> None:
    bundle = _bundle()
    conflicting = replace(
        bundle,
        manifest=replace(bundle.manifest, idempotency_key="different-retry-key"),
    )

    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        committer = GenesisMemoryCommitter()
        committer.commit(bundle, storage)
        with pytest.raises(GenesisValidationError, match="幂等身份"):
            committer.commit(conflicting, storage)


def test_genesis_submission_receipt_is_not_a_writable_graph_node() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as storage:
        with pytest.raises(ValueError, match="unsupported Memory node_type"):
            storage.upsert_node_record(
                NodeInput(
                    node_id="genesis:receipt:genesis-check",
                    node_type="genesis_commit_receipt",
                    canonical_label="Genesis commit receipt",
                )
            )
        assert storage.get_graph_node("genesis:receipt:genesis-check") is None


def test_genesis_submission_receipt_accepts_opaque_submission_identity() -> None:
    receipt = GenesisSubmissionReceipt(
        elfie_id="elfie-a",
        submission_id="genesis-submission-1",
        manifest_id="manifest-1",
        source_version="compiler.v1",
        content_sha256="a" * 64,
        expected_ids_hash="b" * 64,
        committed_at="2026-09-25T10:00:00+00:00",
    )

    assert receipt.submission_id == "genesis-submission-1"
