"""Focused gates for the reviewed source-first Memory contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    MaintenanceRequest,
    MentionInput,
    NodeInput,
    RecallRequest,
)
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.memory.predicates import UnknownPredicateError
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_empty_provisional_store_can_bind_to_final_elfie_identity() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="provisional") as store:
        store.bind_elfie_identity("resident-1")

        assert store.elfie_id == "resident-1"


def test_store_with_memory_cannot_rebind_to_another_elfie() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="owned-memory",
                idempotency_key="owned-memory-key",
                occurred_from="2026-01-01T00:00:00+00:00",
                content_text="This memory belongs to elfie-a.",
            )
        )

        with pytest.raises(
            ValueError,
            match="Memory store is already bound to another Elfie",
        ):
            store.bind_elfie_identity("elfie-b")


def test_unknown_occurrence_time_is_not_replaced_with_a_fake_epoch() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="unknown",
                idempotency_key="unknown-key",
                occurred_from=None,
                occurrence_precision="unknown",
                content_text="rare unknown time memory",
            )
        )
        store.record_episode(
            ClosedEpisode(
                episode_id="dated",
                idempotency_key="dated-key",
                occurred_from="2026-02-01T00:00:00+00:00",
                content_text="rare dated memory",
            )
        )
        raw = store.connection.execute(
            "SELECT occurred_from, occurrence_precision FROM episodes WHERE episode_id='unknown'"
        ).fetchone()
        assert raw[0] is None
        assert raw[1] == "unknown"

        bounded = store.recall(
            RecallRequest(
                text="rare",
                occurred_from="2026-01-01T00:00:00+00:00",
                episode_limit=10,
            )
        )
        assert [episode.episode_id for episode in bounded.episodes] == ["dated"]

        inclusive = store.recall(
            RecallRequest(
                text="rare",
                occurred_from="2026-01-01T00:00:00+00:00",
                include_unknown_time=True,
                episode_limit=10,
            )
        )
        assert {episode.episode_id for episode in inclusive.episodes} == {
            "dated",
            "unknown",
        }


def test_read_back_episode_replays_with_the_original_source_hash() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        original = ClosedEpisode(
            episode_id="read-back",
            idempotency_key="read-back-key",
            occurred_from="2026-01-01T00:00:00+00:00",
            content_text="read back source",
            emotion="curious",
            emotion_intensity=0.7,
            stimulus="owner",
            sensory=(("sight", "warm light"),),
            metadata={
                "owner_note": "keep",
                # These compatibility keys are projected into typed fields by
                # the adapter and must not change the source digest on replay.
                "emotion": "curious",
                "emotion_intensity": 0.7,
                "stimulus": "owner",
                "sensory": {"sight": "warm light"},
            },
        )
        first = store.record_episode(original)
        replay = store.record_episode(store.get_episode(original.episode_id))
        assert first.status == "committed"
        assert replay.status == "duplicate"
        assert replay.content_sha256 == first.content_sha256


def test_importance_is_separate_from_support_and_lifecycle_protects_sources() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="unprojected",
                idempotency_key="unprojected-key",
                occurred_from="2026-01-01T00:00:00+00:00",
                content_text="source remains complete",
                importance=0.8,
            )
        )
        projected_source = ClosedEpisode(
            episode_id="projected",
            idempotency_key="projected-key",
            occurred_from="2026-01-02T00:00:00+00:00",
            content_text="projected source",
            importance=0.8,
        )
        store.record_episode(projected_source)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="projected",
                nodes=(NodeInput("subject", "person", "主人", importance=0.2),),
                evidence=(
                    EvidenceInput(
                        "projected-evidence",
                        "episode",
                        "projected",
                        excerpt="projected source",
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "subject",
                        "knows",
                        object_literal="fact",
                        confidence=0.95,
                        support_score=0.95,
                        importance=0.1,
                        evidence_ids=("projected-evidence",),
                        assertion_id="low-importance-claim",
                    ),
                ),
            )
        )
        claim = store.connection.execute(
            "SELECT importance, confidence, support_score FROM assertions WHERE assertion_id='low-importance-claim'"
        ).fetchone()
        assert tuple(round(float(value), 3) for value in claim) == (0.1, 0.95, 0.95)

        receipt = store.run_lifecycle(MaintenanceRequest(max_episodes=10))
        assert "unprojected" in receipt.lifecycle_episode_ids
        assert "projected" in receipt.lifecycle_episode_ids
        rows = {
            row["episode_id"]: row
            for row in store.connection.execute(
                "SELECT episode_id, detail_level, lifecycle, importance FROM episodes"
            ).fetchall()
        }
        assert rows["unprojected"]["detail_level"] == "full"
        assert rows["unprojected"]["lifecycle"] == "active"
        assert rows["projected"]["detail_level"] == "compressed"
        assert rows["unprojected"]["importance"] == pytest.approx(0.75)
        assert rows["projected"]["importance"] == pytest.approx(0.75)
        assert store.connection.execute(
            "SELECT importance FROM assertions WHERE assertion_id='low-importance-claim'"
        ).fetchone()[0] == pytest.approx(0.05)
        # Lifecycle changes are derived state; they must not invalidate a
        # replay of the immutable Episode source.
        assert (
            store.record_episode(store.get_episode("projected")).status == "duplicate"
        )

        # The due predicate prevents a second immediate pass from applying
        # the same decay contribution again.
        assert (
            store.run_lifecycle(MaintenanceRequest(max_episodes=10)).status == "empty"
        )


def test_genesis_submission_is_atomic_marker_gated_and_retryable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    submission_id = "genesis-submission-1"
    content_hash = _hash("submission-1")
    episode = ClosedEpisode(
        episode_id="genesis-episode",
        idempotency_key="genesis-episode-key",
        occurred_from="2026-01-01T00:00:00+00:00",
        content_text="genesis source",
    )
    node = NodeInput("genesis-node", "concept", "Genesis concept")

    first = SQLiteMemoryStoreAdapter(path, elfie_id="elfie-a")
    observer = SQLiteMemoryStoreAdapter(path, elfie_id="elfie-a")
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            with first.genesis_submission(
                submission_id=submission_id,
                manifest_id="manifest-1",
                source_version="genesis.v1",
                content_sha256=content_hash,
                expected_ids=(episode.episode_id, node.node_id),
            ):
                first.record_episode(episode)
                first.upsert_node_record(node)
                assert observer.get_episode(episode.episode_id) is None
                assert observer.get_graph_node(node.node_id) is None
                raise RuntimeError("injected failure")
        assert first.get_episode(episode.episode_id) is None
        assert first.get_graph_node(node.node_id) is None
        assert (
            first.connection.execute(
                "SELECT COUNT(*) FROM memory_genesis_submissions"
            ).fetchone()[0]
            == 0
        )

        with first.genesis_submission(
            submission_id=submission_id,
            manifest_id="manifest-1",
            source_version="genesis.v1",
            content_sha256=content_hash,
            expected_ids=(episode.episode_id, node.node_id),
        ) as accepted:
            assert accepted is True
            first.record_episode(episode)
            first.upsert_node_record(node)

        assert observer.get_episode(episode.episode_id) is not None
        assert observer.get_graph_node(node.node_id) is not None
        tags = {
            row[0]
            for row in first.connection.execute(
                "SELECT genesis_submission_id FROM episodes WHERE episode_id=? "
                "UNION ALL SELECT genesis_submission_id FROM nodes WHERE node_id=?",
                (episode.episode_id, node.node_id),
            ).fetchall()
        }
        assert tags == {submission_id}

        with first.genesis_submission(
            submission_id=submission_id,
            manifest_id="manifest-1",
            source_version="genesis.v1",
            content_sha256=content_hash,
            expected_ids=(episode.episode_id, node.node_id),
        ) as accepted:
            assert accepted is False
        with pytest.raises(ValueError, match="different hash"):
            with first.genesis_submission(
                submission_id=submission_id,
                manifest_id="manifest-1",
                source_version="genesis.v1",
                content_sha256=_hash("different"),
            ):
                pass

        # A higher-level Genesis operation may submit another atomic package
        # under the same manifest.  Memory owns submission-level idempotence,
        # not Genesis batching policy; a different manifest is still rejected.
        with first.genesis_submission(
            submission_id="genesis-submission-2",
            manifest_id="manifest-1",
            source_version="genesis.v1",
            content_sha256=_hash("submission-2"),
        ) as accepted:
            assert accepted is True
            first.upsert_node_record(NodeInput("genesis-node-2", "concept", "第二批"))
        assert first.get_graph_node("genesis-node-2") is not None
        assert (
            first.connection.execute(
                "SELECT COUNT(*) FROM memory_genesis_submissions WHERE elfie_id='elfie-a'"
            ).fetchone()[0]
            == 2
        )
        with pytest.raises(ValueError, match="different Genesis manifest"):
            with first.genesis_submission(
                submission_id="genesis-submission-3",
                manifest_id="manifest-2",
                source_version="genesis.v1",
                content_sha256=_hash("submission-3"),
            ):
                pass
    finally:
        observer.close()
        first.close()


def test_unknown_predicate_rolls_back_and_leaves_a_diagnostic() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode("episode-1", "key-1", "2026-01-01", "bounded source")
        )
        with pytest.raises(UnknownPredicateError):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id="episode-1",
                    nodes=(NodeInput("candidate", "concept", "候选"),),
                    evidence=(
                        EvidenceInput(
                            "candidate-evidence",
                            "episode",
                            "episode-1",
                            excerpt="bounded source",
                        ),
                    ),
                    assertions=(
                        AssertionInput(
                            "candidate",
                            "not_in_registry",
                            object_literal="value",
                            evidence_ids=("candidate-evidence",),
                        ),
                    ),
                )
            )
        assert store.get_graph_node("candidate") is None
        assert (
            store.connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE evidence_id='candidate-evidence'"
            ).fetchone()[0]
            == 0
        )
        assert (
            store.connection.execute(
                "SELECT COUNT(*) FROM projection_diagnostics WHERE episode_id='episode-1'"
            ).fetchone()[0]
            == 1
        )


def test_nested_projection_failure_keeps_diagnostic_after_outer_rollback() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode("episode-outer", "key-outer", "2026-01-01", "bounded source")
        )
        with pytest.raises(UnknownPredicateError):
            with store.write_transaction():
                store.apply_consolidation(
                    ConsolidationProjection(
                        episode_id="episode-outer",
                        assertions=(
                            AssertionInput(
                                "missing-subject",
                                "not_in_registry",
                                object_literal="value",
                                evidence_ids=("missing-evidence",),
                            ),
                        ),
                    )
                )
        assert (
            store.connection.execute(
                "SELECT COUNT(*) FROM projection_diagnostics WHERE episode_id='episode-outer'"
            ).fetchone()[0]
            == 1
        )


def test_typed_literal_type_is_part_of_assertion_identity() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode("typed-episode", "typed-key", "2026-01-01", "typed source")
        )
        for suffix, literal_type in (("date", "date"), ("text", "string")):
            evidence_id = f"typed-evidence-{suffix}"
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id="typed-episode",
                    evidence=(
                        EvidenceInput(
                            evidence_id,
                            "episode",
                            "typed-episode",
                            excerpt="typed source",
                        ),
                    ),
                    assertions=(
                        AssertionInput(
                            "typed-subject",
                            "knows",
                            object_literal="2026-01-01",
                            object_literal_type=literal_type,
                            evidence_ids=(evidence_id,),
                            assertion_id=f"typed-claim-{suffix}",
                        ),
                    ),
                    nodes=(NodeInput("typed-subject", "person", "主人"),),
                )
            )
        claims = store.graph_assertions_for(
            ("typed-subject",), relation_types=("knows",)
        )
        assert {claim.assertion_id for claim in claims} == {
            "typed-claim-date",
            "typed-claim-text",
        }


def test_bound_adapters_cannot_read_another_elfies_graph_or_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    first = SQLiteMemoryStoreAdapter(path, elfie_id="elfie-a")
    second = SQLiteMemoryStoreAdapter(path, elfie_id="elfie-b")
    try:
        first.add_edge("a-node", "b-node", "knows")
        evidence_id = (
            "legacy-edge:" + hashlib.sha256(b"a-node|b-node|knows").hexdigest()[:24]
        )
        assert second.get_node("a-node") is None
        assert second.resolve_graph_node_id("a-node") is None
        assert second.get_edges("a-node") == []
        assert second.graph_assertions_for(("a-node",)) == ()
        assert second.get_evidence(evidence_id) is None
        assert second.get_assertion_evidence_for_ids((evidence_id,)) == ()
    finally:
        second.close()
        first.close()


def test_bound_adapter_does_not_claim_an_unbound_graph_row(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(path) as unbound:
        unbound.upsert_node_record(NodeInput("unbound-node", "concept", "未绑定"))

    with SQLiteMemoryStoreAdapter(path, elfie_id="elfie-a") as bound:
        with pytest.raises(ValueError, match="unbound namespace"):
            bound.upsert_node_record(NodeInput("unbound-node", "concept", "未绑定"))


def test_recall_facets_are_positive_and_combine_across_families() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for episode_id, emotion, topic, cause, include_place in (
            ("matching", "joy", "travel", "rain", True),
            ("missing-place", "joy", "travel", "rain", False),
            ("wrong-emotion", "sad", "travel", "rain", True),
        ):
            store.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=episode_id + "-key",
                    occurred_from="2026-01-01T00:00:00+00:00",
                    content_text="rare blue garden memory",
                    emotion=emotion,
                    metadata={"topic": topic, "cause": cause},
                )
            )
            nodes = [NodeInput("person", "person", "主人")]
            mentions = [
                MentionInput(episode_id, "主人", "person", "resolved", role="person")
            ]
            if include_place:
                nodes.append(NodeInput("place", "place", "花园"))
                mentions.append(
                    MentionInput(episode_id, "花园", "place", "resolved", role="place")
                )
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=tuple(nodes),
                    mentions=tuple(mentions),
                    evidence=(
                        EvidenceInput(
                            "evidence-" + episode_id,
                            "episode",
                            episode_id,
                            excerpt="rare blue garden memory",
                        ),
                    ),
                )
            )
        bundle = store.recall(
            RecallRequest(
                text="rare blue",
                person_node_ids=("person",),
                place_node_ids=("place",),
                emotion_labels=("joy",),
                topic_labels=("travel",),
                cause_labels=("rain",),
                episode_limit=10,
            )
        )
        assert [episode.episode_id for episode in bundle.episodes] == ["matching"]


def test_recall_privacy_scope_filters_sources_and_graph_nodes() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for episode_id, scope in (("private", "private"), ("shared", "shared")):
            store.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=episode_id + "-key",
                    occurred_from="2026-01-01T00:00:00+00:00",
                    content_text="privacy boundary memory",
                    privacy_scope=scope,
                )
            )
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(
                        NodeInput(
                            "privacy-node-" + scope,
                            "concept",
                            "隐私边界",
                            properties={"privacy_scope": scope},
                        ),
                    ),
                    evidence=(
                        EvidenceInput(
                            "privacy-evidence-" + scope,
                            "episode",
                            episode_id,
                            excerpt="privacy boundary memory",
                        ),
                    ),
                )
            )
        private_bundle = store.recall(
            RecallRequest(text="privacy boundary", privacy_scope="private")
        )
        assert {episode.episode_id for episode in private_bundle.episodes} == {
            "private"
        }
        assert all(
            node.node_id == "privacy-node-private"
            for node in private_bundle.focus_nodes
        )
        shared_bundle = store.recall(
            RecallRequest(text="privacy boundary", privacy_scope="shared")
        )
        assert {episode.episode_id for episode in shared_bundle.episodes} == {"shared"}
        assert all(
            node.node_id == "privacy-node-shared" for node in shared_bundle.focus_nodes
        )


def test_recall_keeps_superseded_claims_after_an_explicit_correction() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for episode_id, content in (("old", "old name"), ("new", "new name")):
            store.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=episode_id + "-key",
                    occurred_from="2026-01-01T00:00:00+00:00",
                    content_text=content,
                )
            )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="old",
                nodes=(NodeInput("owner", "person", "主人"),),
                evidence=(
                    EvidenceInput("old-evidence", "episode", "old", excerpt="old name"),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "preferred_name",
                        object_literal="旧名",
                        evidence_ids=("old-evidence",),
                        assertion_id="old-claim",
                    ),
                ),
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="new",
                evidence=(
                    EvidenceInput("new-evidence", "episode", "new", excerpt="new name"),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "preferred_name",
                        object_literal="新名",
                        context="correction",
                        evidence_ids=("new-evidence",),
                        assertion_id="new-claim",
                    ),
                ),
            )
        )
        claims = store.graph_assertions_for(
            ("owner",), relation_types=("preferred_name",)
        )
        assert {claim.assertion_id for claim in claims} == {"old-claim", "new-claim"}
        assert {claim.status for claim in claims} == {"active", "superseded"}


def test_memory_maintenance_exposes_ordered_consolidation_counts() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        memory = MemorySystem(store, elfie_id="elfie-a")
        memory.record_closed_episode(
            ClosedEpisode(
                episode_id="maintenance-episode",
                idempotency_key="maintenance-key",
                occurred_from="2026-01-01T00:00:00+00:00",
                content_text="主人喜欢香菜。",
            )
        )
        receipt = memory.run_maintenance(MaintenanceRequest(max_episodes=1))
        assert receipt.consolidated_episode_ids == ("maintenance-episode",)
        assert receipt.knowledge_created >= 1
        assert receipt.edges_created >= 1
        assert receipt.status in {"completed", "partial"}
