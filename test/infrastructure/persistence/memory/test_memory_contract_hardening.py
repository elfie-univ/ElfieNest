"""Focused gates for the reviewed source-first Memory contract."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from elfie.brain.consolidation.system import CognitiveConsolidationSystem
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
from infrastructure.persistence.memory import (
    SQLiteMemoryStoreAdapter,
    sqlite_lifecycle_store,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def test_importance_and_confidence_are_separate_and_lifecycle_protects_sources() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="unprojected",
                idempotency_key="unprojected-key",
                occurred_from="2026-01-01T00:00:00+00:00",
                content_text="source remains complete",
                importance=0.8,
                last_reinforced_at="2020-01-01T00:00:00+00:00",
            )
        )
        projected_source = ClosedEpisode(
            episode_id="projected",
            idempotency_key="projected-key",
            occurred_from="2026-01-02T00:00:00+00:00",
            content_text="projected source",
            importance=0.8,
            last_reinforced_at="2020-01-01T00:00:00+00:00",
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
                        importance=0.1,
                        evidence_ids=("projected-evidence",),
                        assertion_id="low-importance-claim",
                    ),
                ),
            )
        )
        store.connection.execute(
            "UPDATE episodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' "
            "WHERE episode_id='projected'"
        )
        store.connection.execute(
            "UPDATE assertions SET last_reinforced_at='2020-01-01T00:00:00+00:00' "
            "WHERE assertion_id='low-importance-claim'"
        )
        store.connection.commit()
        claim = store.connection.execute(
            "SELECT importance, confidence FROM assertions WHERE assertion_id='low-importance-claim'"
        ).fetchone()
        # Retention v3 recomputes confidence from the immutable .95 prior and
        # the observed .9 Evidence contribution, rather than applying the v1
        # arrival-order increment.
        assert tuple(round(float(value), 3) for value in claim) == (0.1, 0.974)

        receipt = store.run_lifecycle(MaintenanceRequest(max_episodes=10))
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
        assert rows["unprojected"]["importance"] == pytest.approx(0.8)
        assert rows["projected"]["importance"] == pytest.approx(0.8)
        claim_after = store.connection.execute(
            "SELECT importance, confidence, lifecycle FROM assertions WHERE assertion_id='low-importance-claim'"
        ).fetchone()
        assert claim_after is not None
        assert float(claim_after[0]) == pytest.approx(0.1)
        assert float(claim_after[1]) == pytest.approx(0.9736842105)
        assert claim_after[2] == "archived"
        # Lifecycle changes are derived state; they must not invalidate a
        # replay of the immutable Episode source.
        assert (
            store.record_episode(store.get_episode("projected")).status == "duplicate"
        )

        # A second pass may advance the next one-stage lifecycle boundary,
        # but it never applies the same transition or changes a score.
        second = store.run_lifecycle(MaintenanceRequest(max_episodes=10))
        assert second.lifecycle_episode_ids == ("projected",)
        assert store.get_episode("projected").detail_level == "digest"


def test_distinct_evidence_reinforces_a_claim_once_and_replay_is_idempotent() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for episode_id, key, content in (
            ("episode-score-1", "score-key-1", "主人喜欢香菜"),
            ("episode-score-2", "score-key-2", "主人仍然喜欢香菜"),
        ):
            store.record_episode(
                ClosedEpisode(
                    episode_id=episode_id,
                    idempotency_key=key,
                    occurred_from="2026-01-01T00:00:00+00:00",
                    content_text=content,
                )
            )
        first = ConsolidationProjection(
            episode_id="episode-score-1",
            nodes=(
                NodeInput("owner", "person", "主人", importance=0.4),
                NodeInput("food", "food", "香菜", importance=0.4),
            ),
            evidence=(EvidenceInput("score-evidence-1", "episode", "episode-score-1"),),
            assertions=(
                AssertionInput(
                    "owner",
                    "likes",
                    object_node_id="food",
                    evidence_ids=("score-evidence-1",),
                    confidence=0.5,
                    importance=0.4,
                ),
            ),
        )
        store.apply_consolidation(first)
        claim_id = store.connection.execute(
            "SELECT assertion_id FROM assertions"
        ).fetchone()[0]
        before = store.connection.execute(
            "SELECT confidence, importance FROM assertions WHERE assertion_id=?",
            (claim_id,),
        ).fetchone()

        second = ConsolidationProjection(
            episode_id="episode-score-2",
            nodes=(
                NodeInput("owner-2", "person", "主人"),
                NodeInput("food-2", "food", "香菜"),
            ),
            evidence=(EvidenceInput("score-evidence-2", "episode", "episode-score-2"),),
            assertions=(
                AssertionInput(
                    "owner-2",
                    "likes",
                    object_node_id="food-2",
                    evidence_ids=("score-evidence-2",),
                    confidence=0.5,
                    importance=0.4,
                ),
            ),
        )
        store.apply_consolidation(second)
        after = store.connection.execute(
            "SELECT confidence, importance FROM assertions WHERE assertion_id=?",
            (claim_id,),
        ).fetchone()
        assert after[0] > before[0]
        assert after[1] == pytest.approx(before[1])

        # Replaying the same projection is a duplicate and must not add a
        # second semantic contribution for the same stable evidence link.
        store.apply_consolidation(second)
        replay = store.connection.execute(
            "SELECT confidence, importance FROM assertions WHERE assertion_id=?",
            (claim_id,),
        ).fetchone()
        assert tuple(replay) == (after[0], after[1])


def test_recall_ranks_direct_match_before_stronger_second_hop() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                "episode-rank",
                "rank-key",
                "2026-01-01T00:00:00+00:00",
                "主人喜欢香菜，香菜在厨房。",
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-rank",
                nodes=(
                    NodeInput("owner", "person", "主人"),
                    NodeInput("food", "food", "香菜"),
                    NodeInput("place", "place", "厨房"),
                ),
                evidence=(EvidenceInput("rank-evidence", "episode", "episode-rank"),),
                assertions=(
                    AssertionInput(
                        "owner",
                        "likes",
                        object_node_id="food",
                        importance=0.1,
                        evidence_ids=("rank-evidence",),
                        assertion_id="direct-claim",
                    ),
                    AssertionInput(
                        "food",
                        "at",
                        object_node_id="place",
                        importance=0.9,
                        evidence_ids=("rank-evidence",),
                        assertion_id="second-hop-claim",
                    ),
                ),
            )
        )

        bundle = store.recall(
            RecallRequest(
                seed_node_ids=("owner",),
                mode="local",
                hop_limit=2,
                assertion_limit=8,
            )
        )

        assert [item.assertion_id for item in bundle.assertions[:2]] == [
            "direct-claim",
            "second-hop-claim",
        ]


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
        first.record_episode(
            ClosedEpisode(
                "namespace-episode",
                "namespace-key",
                "2026-01-01T00:00:00+00:00",
                "主人认识小狐",
            )
        )
        first.upsert_node_record(NodeInput("a-node", "person", "主人"))
        first.upsert_node_record(NodeInput("b-node", "animal", "小狐"))
        first.record_sourced_assertion(
            AssertionInput(
                "a-node",
                "knows",
                object_node_id="b-node",
                assertion_id="namespace-claim",
                evidence_ids=("namespace-evidence",),
            ),
            EvidenceInput(
                "namespace-evidence",
                "episode",
                "namespace-episode",
                excerpt="主人认识小狐",
            ),
        )
        assert second.get_graph_node("a-node") is None
        assert second.resolve_graph_node_id("a-node") is None
        assert second.graph_assertions_for(("a-node",)) == ()
        assert second.get_assertion_evidence(("namespace-claim",)) == ()
    finally:
        second.close()
        first.close()


def test_empty_memory_store_can_rebind_a_provisional_identity() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="provisional") as store:
        store.bind_elfie_identity("resident-1")
        assert store.elfie_id == "resident-1"


def test_nonempty_memory_store_rejects_identity_rebind() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="provisional") as store:
        store.record_episode(
            ClosedEpisode(
                "identity-bound-source",
                "identity-bound-key",
                "2026-01-01T00:00:00+00:00",
                "已属于临时精灵的来源",
            )
        )
        with pytest.raises(ValueError, match="already bound"):
            store.bind_elfie_identity("resident-1")


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
    class MaintenanceModel:
        def ask_with_food(self, **_kwargs: object) -> str:
            return (
                '{"nodes":[{"label":"主人","type":"person"},'
                '{"label":"香菜","type":"food"}],"mentions":[],'
                '"assertions":[{"subject_ref":"主人","predicate":"likes",'
                '"object_ref":"香菜","confidence":0.8,"importance_event":"major"}]}'
            )

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
        receipt = memory.run_maintenance(
            MaintenanceRequest(max_episodes=1), model_port=MaintenanceModel()
        )
        assert receipt.consolidated_episode_ids == ("maintenance-episode",)
        assert receipt.knowledge_created >= 1
        assert receipt.edges_created >= 1
        assert receipt.status in {"completed", "partial"}


def test_memory_maintenance_uses_one_budget_across_both_stages() -> None:
    class MaintenanceModel:
        def ask_with_food(self, **_kwargs: object) -> str:
            return (
                '{"nodes":[{"label":"待投影来源","type":"concept"}],'
                '"mentions":[],"assertions":[]}'
            )

    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        memory = MemorySystem(store, elfie_id="elfie-a")
        memory.record_closed_episode(
            ClosedEpisode(
                "budget-episode",
                "budget-episode-key",
                "2026-01-01T00:00:00+00:00",
                "待投影来源",
            )
        )
        store.upsert_node_record(
            NodeInput(
                "budget-node",
                "concept",
                "待维护节点",
                importance=0.8,
                properties={"elfie_id": "elfie-a"},
            )
        )
        store.connection.execute(
            "UPDATE nodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' WHERE node_id='budget-node'"
        )
        store.connection.commit()

        receipt = memory.run_maintenance(
            MaintenanceRequest(max_episodes=1), model_port=MaintenanceModel()
        )

        assert receipt.consolidated_episode_ids == ("budget-episode",)
        assert receipt.lifecycle_node_ids == ()
        importance = store.connection.execute(
            "SELECT importance FROM nodes WHERE node_id='budget-node'"
        ).fetchone()[0]
        assert importance == 0.8


def test_fresh_memory_is_not_immediately_due_for_lifecycle() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                "fresh-episode",
                "fresh-key",
                "2026-08-29T00:00:00+00:00",
                "fresh source",
            )
        )
        store.upsert_node_record(NodeInput("fresh-node", "concept", "fresh concept"))
        store.record_sourced_assertion(
            AssertionInput(
                "fresh-node",
                "about",
                object_literal="fresh source",
                evidence_ids=("fresh-evidence",),
            ),
            EvidenceInput(
                "fresh-evidence",
                "episode",
                "fresh-episode",
                excerpt="fresh source",
            ),
        )
        assert store.has_due_lifecycle() is False
        assert store.run_lifecycle(MaintenanceRequest(max_episodes=8)).status == "empty"


def test_typed_memory_initialization_and_inspection_use_only_source_first_records() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        memory = MemorySystem(
            store,
            elfie_id="elfie-a",
            personality_data={"self_description": "一只谨慎的精灵"},
        )
        assert memory.uses_typed_memory is True
        assert not hasattr(memory, "encoder")
        assert not hasattr(memory, "retriever")
        assert not hasattr(memory, "recall_formatter")

        store.record_episode(
            ClosedEpisode(
                "inspection-episode",
                "inspection-key",
                "2026-08-29T00:00:00+00:00",
                "在花园观察蝴蝶",
                emotion="curious",
            )
        )
        store.upsert_node_record(
            NodeInput(
                "inspection-node",
                "place",
                "花园",
                properties={"elfie_id": "elfie-a", "core_key": "world"},
            )
        )

        snapshot = memory.memory_inspection_snapshot(
            episode_limit=4,
            node_limit=4,
            assertion_limit=4,
        )
        assert [episode.episode_id for episode in snapshot.episodes] == [
            "inspection-episode"
        ]
        assert snapshot.nodes[0].properties["core_key"] == "world"


def test_lifecycle_only_work_wakes_memory_maintenance() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.upsert_node_record(
            NodeInput(
                "due-node",
                "concept",
                "历史概念",
                properties={"elfie_id": "elfie-a"},
            )
        )
        store.connection.execute(
            "UPDATE nodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' WHERE node_id='due-node'"
        )
        store.connection.commit()
        memory = MemorySystem(store, elfie_id="elfie-a")

        assert memory.pending_consolidation_ids() == ("maintenance:lifecycle",)


def test_lifecycle_only_scheduler_candidate_runs_memory_maintenance() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.upsert_node_record(
            NodeInput(
                "scheduler-due-node",
                "concept",
                "仅生命周期维护",
                importance=0.8,
                properties={"elfie_id": "elfie-a"},
            )
        )
        store.connection.execute(
            "UPDATE nodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' WHERE node_id='scheduler-due-node'"
        )
        store.connection.commit()
        memory = MemorySystem(store, elfie_id="elfie-a")
        now = datetime.now(timezone.utc)
        calls: list[int] = []
        system = CognitiveConsolidationSystem(
            pending_episode_ids=memory.pending_consolidation_ids,
            consolidate=lambda limit: (
                calls.append(limit) or _maintenance_result(memory, limit)
            ),
            initial_at=now,
        )

        candidate = system.evaluate(
            sleeping=True,
            now=now + timedelta(seconds=1),
            blocked=False,
        )
        assert candidate is not None
        assert candidate.episode_ids == ("maintenance:lifecycle",)
        assert system.settle(
            candidate.candidate_id,
            now=now + timedelta(seconds=2),
            success=True,
        )
        assert calls == [1]
        assert store.connection.execute(
            "SELECT importance FROM nodes WHERE node_id='scheduler-due-node'"
        ).fetchone()[0] == pytest.approx(0.8)


def _maintenance_result(memory: MemorySystem, limit: int) -> dict[str, int]:
    receipt = memory.run_maintenance(MaintenanceRequest(max_episodes=limit))
    return {
        "consolidated_count": len(receipt.consolidated_episode_ids),
        "knowledge_created": receipt.knowledge_created,
        "patterns_created": receipt.patterns_created,
    }


def test_lifecycle_checkpoint_resumes_after_the_last_claimed_target() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for node_id in ("due-a", "due-b"):
            store.upsert_node_record(
                NodeInput(
                    node_id,
                    "concept",
                    node_id,
                    properties={"elfie_id": "elfie-a"},
                )
            )
        store.connection.execute(
            "UPDATE nodes SET last_reinforced_at='2020-01-01T00:00:00+00:00'"
        )
        store.connection.commit()

        first = store.run_lifecycle(MaintenanceRequest(max_episodes=1))
        assert first.lifecycle_node_ids == ("due-a",)
        assert first.checkpoint
        second = store.run_lifecycle(
            MaintenanceRequest(max_episodes=1, checkpoint=first.checkpoint)
        )
        assert second.lifecycle_node_ids == ("due-b",)


def test_failed_lifecycle_target_remains_retryable_with_the_prior_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for episode_id in ("due-a", "due-b"):
            store.record_episode(
                ClosedEpisode(
                    episode_id,
                    f"{episode_id}-key",
                    "2020-01-01T00:00:00+00:00",
                    episode_id,
                    last_reinforced_at="2020-01-01T00:00:00+00:00",
                )
            )
        store.connection.execute(
            "UPDATE episodes SET projection_revision='fixture', "
            "projection_source_sha256=content_sha256"
        )
        store.connection.commit()

        first = store.run_lifecycle(MaintenanceRequest(max_episodes=1))
        assert first.lifecycle_episode_ids == ("due-a",)

        def fail_review(*_args: object, **_kwargs: object) -> str:
            raise RuntimeError("injected lifecycle failure")

        monkeypatch.setattr(
            sqlite_lifecycle_store, "_next_lifecycle_review", fail_review
        )
        failed = store.run_lifecycle(
            MaintenanceRequest(max_episodes=1, checkpoint=first.checkpoint)
        )
        assert failed.lifecycle_episode_ids == ()
        assert failed.errors["due-b"] == "injected lifecycle failure"
        assert failed.checkpoint == first.checkpoint

        monkeypatch.undo()
        store.connection.execute(
            "UPDATE memory_maintenance SET next_attempt_at='1970-01-01T00:00:00+00:00' WHERE target_id='due-b'"
        )
        store.connection.commit()
        retried = store.run_lifecycle(
            MaintenanceRequest(max_episodes=1, checkpoint=first.checkpoint)
        )
        assert retried.lifecycle_episode_ids == ("due-b",)


def test_lifecycle_checkpoint_does_not_skip_failure_before_later_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        for episode_id in ("due-a", "due-b", "due-c"):
            store.record_episode(
                ClosedEpisode(
                    episode_id,
                    f"{episode_id}-key",
                    "2020-01-01T00:00:00+00:00",
                    episode_id,
                    last_reinforced_at="2020-01-01T00:00:00+00:00",
                )
            )
        store.connection.execute(
            "UPDATE episodes SET projection_revision='fixture', "
            "projection_source_sha256=content_sha256"
        )
        store.connection.commit()

        first = store.run_lifecycle(MaintenanceRequest(max_episodes=1))
        assert first.lifecycle_episode_ids == ("due-a",)

        original_next_review = sqlite_lifecycle_store._next_lifecycle_review
        calls = 0

        def fail_once(
            anchor: str, half_life_days: float, detail_level: str, lifecycle: str
        ) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected earlier failure")
            return original_next_review(anchor, half_life_days, detail_level, lifecycle)

        monkeypatch.setattr(sqlite_lifecycle_store, "_next_lifecycle_review", fail_once)
        failed_then_success = store.run_lifecycle(
            MaintenanceRequest(max_episodes=2, checkpoint=first.checkpoint)
        )
        assert failed_then_success.lifecycle_episode_ids == ("due-c",)
        assert failed_then_success.errors["due-b"] == "injected earlier failure"
        assert failed_then_success.checkpoint == first.checkpoint

        monkeypatch.undo()
        store.connection.execute(
            "UPDATE memory_maintenance SET next_attempt_at='1970-01-01T00:00:00+00:00' WHERE target_id='due-b'"
        )
        store.connection.commit()
        retried = store.run_lifecycle(
            MaintenanceRequest(
                max_episodes=1, checkpoint=failed_then_success.checkpoint
            )
        )
        assert retried.lifecycle_episode_ids == ("due-b",)


def test_stale_lifecycle_worker_cannot_publish_after_claim_changes() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.upsert_node_record(
            NodeInput(
                "fenced-node",
                "concept",
                "不可被旧 worker 覆盖",
                importance=0.8,
                properties={"elfie_id": "elfie-a"},
            )
        )
        store.connection.execute(
            "UPDATE nodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' WHERE node_id='fenced-node'"
        )
        store.connection.commit()

        original_claim = store._claim_maintenance_target

        def claim_then_replace(**kwargs):
            attempt = original_claim(**kwargs)
            if attempt is not None:
                store.connection.execute(
                    """UPDATE memory_maintenance
                          SET lease_owner='new-worker', attempts=attempts+1,
                              lease_until='2099-01-01T00:00:00+00:00'
                        WHERE elfie_id=? AND stage=? AND target_id=?""",
                    ("elfie-a", "lifecycle", kwargs["target_id"]),
                )
            return attempt

        store._claim_maintenance_target = claim_then_replace
        receipt = store.run_lifecycle(
            MaintenanceRequest(max_episodes=1, worker_id="old-worker")
        )

        assert receipt.status == "failed"
        assert "fenced-node" in receipt.errors
        row = store.connection.execute(
            "SELECT importance FROM nodes WHERE node_id='fenced-node'"
        ).fetchone()
        assert row[0] == 0.8
        claim = store.connection.execute(
            """SELECT state, lease_owner, attempts
                 FROM memory_maintenance
                WHERE elfie_id='elfie-a' AND stage='lifecycle'
                  AND target_id='fenced-node'"""
        ).fetchone()
        assert tuple(claim) == ("processing", "new-worker", 2)


def test_expired_lifecycle_lease_is_recovered() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.connection.execute(
            """INSERT INTO memory_maintenance(
                   work_id, elfie_id, stage, target_id, state, attempts,
                   lease_owner, lease_until, updated_at
               ) VALUES ('lifecycle:expired', 'elfie-a', 'lifecycle',
                         'expired', 'processing', 1, 'dead-worker',
                         '1970-01-01T00:00:00+00:00', '1970-01-01T00:00:00+00:00')"""
        )
        store.connection.commit()

        assert store.recover_expired_maintenance_leases() == 1
        row = store.connection.execute(
            "SELECT state, lease_owner, lease_until, next_attempt_at FROM memory_maintenance"
        ).fetchone()
        assert tuple(row[:3]) == ("failed", None, None)
        assert row[3]


def test_forgetting_requires_a_current_hash_bound_evidence_trail() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        source = ClosedEpisode(
            "forget-source",
            "forget-source-key",
            "2026-01-01T00:00:00+00:00",
            "完整来源内容",
        )
        store.record_episode(source)
        assert store.forget_episode(source.episode_id) is False

        projected = ClosedEpisode(
            "forget-projected",
            "forget-projected-key",
            "2026-01-01T00:00:00+00:00",
            "可审计来源内容",
        )
        store.record_episode(projected)
        stored = store.get_episode(projected.episode_id)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=projected.episode_id,
                nodes=(NodeInput("forget-node", "concept", "可审计"),),
                evidence=(
                    EvidenceInput(
                        "forget-evidence",
                        "episode",
                        projected.episode_id,
                        excerpt=projected.content_text,
                        source_sha256=stored.content_sha256,
                    ),
                ),
            )
        )
        assert store.forget_episode(projected.episode_id) is True
        forgotten = store.get_episode(projected.episode_id)
        assert forgotten.detail_level == "digest"
        assert forgotten.content_text.startswith("[forgotten:")


def test_projected_lifecycle_compacts_then_digests_then_archives() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        episode = ClosedEpisode(
            "lifecycle-stages",
            "lifecycle-stages-key",
            "2026-01-01T00:00:00+00:00",
            "需要分阶段维护的来源",
            last_reinforced_at="2020-01-01T00:00:00+00:00",
        )
        store.record_episode(episode)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=episode.episode_id,
                nodes=(NodeInput("lifecycle-node", "concept", "维护"),),
                evidence=(
                    EvidenceInput(
                        "lifecycle-evidence",
                        "episode",
                        episode.episode_id,
                        excerpt=episode.content_text,
                        source_sha256=store.get_episode(
                            episode.episode_id
                        ).content_sha256,
                    ),
                ),
            )
        )
        store.connection.execute(
            "UPDATE episodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' "
            "WHERE episode_id=?",
            (episode.episode_id,),
        )
        store.connection.commit()
        first = store.run_lifecycle(MaintenanceRequest(max_episodes=1))
        assert first.lifecycle_episode_ids == (episode.episode_id,)
        assert store.get_episode(episode.episode_id).detail_level == "compressed"

        store.run_lifecycle(MaintenanceRequest(max_episodes=1))
        digested = store.get_episode(episode.episode_id)
        assert digested.detail_level == "digest"
        assert digested.content_text.startswith("[digest:")

        store.run_lifecycle(MaintenanceRequest(max_episodes=1))
        lifecycle = store.connection.execute(
            "SELECT lifecycle FROM episodes WHERE episode_id=?",
            (episode.episode_id,),
        ).fetchone()[0]
        assert lifecycle == "archived"


def test_lifecycle_forgets_archived_low_importance_episode_after_dependencies_are_safe() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        episode = ClosedEpisode(
            "lifecycle-forget",
            "lifecycle-forget-key",
            "2020-01-01T00:00:00+00:00",
            "一段低重要性且已有完整证据的来源",
            importance=0.1,
            last_reinforced_at="2020-01-01T00:00:00+00:00",
        )
        store.record_episode(episode)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=episode.episode_id,
                nodes=(NodeInput("lifecycle-forget-node", "concept", "低重要性"),),
                evidence=(
                    EvidenceInput(
                        "lifecycle-forget-evidence",
                        "episode",
                        episode.episode_id,
                        excerpt=episode.content_text,
                        source_sha256=store.get_episode(
                            episode.episode_id
                        ).content_sha256,
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "lifecycle-forget-node",
                        "knows",
                        object_literal="低重要性来源",
                        evidence_ids=("lifecycle-forget-evidence",),
                    ),
                ),
            )
        )
        store.connection.execute(
            "UPDATE episodes SET last_reinforced_at='2020-01-01T00:00:00+00:00' "
            "WHERE episode_id=?",
            (episode.episode_id,),
        )
        store.connection.commit()

        expected_stages = (
            ("active", "compressed"),
            ("active", "digest"),
            ("archived", "digest"),
            ("forgotten", "digest"),
        )
        for expected_lifecycle, expected_detail in expected_stages:
            receipt = store.run_lifecycle(MaintenanceRequest(max_episodes=1))
            assert receipt.lifecycle_episode_ids == (episode.episode_id,)
            current = store.get_episode(episode.episode_id)
            assert current.lifecycle == expected_lifecycle
            assert current.detail_level == expected_detail
            if expected_lifecycle == "archived":
                # Logical forgetting is intentionally delayed by the
                # 90-day archived safety window.
                store.connection.execute(
                    "UPDATE episodes SET lifecycle_changed_at='2020-01-01T00:00:00+00:00' "
                    "WHERE episode_id=?",
                    (episode.episode_id,),
                )
                store.connection.commit()

        forgotten = store.get_episode(episode.episode_id)
        assert forgotten.lifecycle == "forgotten"
        assert forgotten.detail_level == "digest"
        assert forgotten.content_text.startswith("[forgotten:")
        assert store.get_episode(episode.episode_id) is not None
        assert store.list_episodes() == ()
