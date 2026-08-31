"""Behavioral gates for the Retention v3 score and feedback contract."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from elfie.brain.memory.memory_records import (
    AliasInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    MemoryUseProposal,
    MentionInput,
    NodeInput,
    QualifiedReinforcementReceipt,
    RecallRequest,
)
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.memory.score_policy import ImportanceEvent, MemoryScorePolicy
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _episode(episode_id: str, *, occurred_at: datetime | None = None) -> ClosedEpisode:
    occurred = occurred_at or _now()
    return ClosedEpisode(
        episode_id=episode_id,
        idempotency_key=episode_id + ":key",
        occurred_from=occurred.isoformat(),
        content_text="retention v3 source " + episode_id,
    )


def test_admission_profile_owns_initial_half_life_and_is_persisted() -> None:
    occurred = _now() - timedelta(hours=1)
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        store.record_episode(
            ClosedEpisode(
                episode_id="profile-transient",
                idempotency_key="profile-transient:key",
                occurred_from=occurred.isoformat(),
                content_text="transient detail",
                half_life_days=365.0,
                retention_profile="transient",
            )
        )
        store.record_episode(
            ClosedEpisode(
                episode_id="profile-salient",
                idempotency_key="profile-salient:key",
                occurred_from=occurred.isoformat(),
                content_text="salient event",
                half_life_days=0.5,
                retention_profile="salient",
            )
        )
        store.upsert_node_record(
            NodeInput(
                "profile-node",
                "person",
                "稳定身份",
                half_life_days=0.5,
                retention_profile="stable",
            )
        )
        store.record_sourced_assertion(
            AssertionInput(
                "profile-node",
                "about",
                object_literal="semantic fact",
                half_life_days=365.0,
                retention_profile="semantic",
            ),
            EvidenceInput("profile-evidence", "seed", "profile-seed"),
        )

        episode_rows = {
            str(row[0]): (str(row[1]), float(row[2]))
            for row in store.connection.execute(
                "SELECT episode_id, retention_profile, half_life_days FROM episodes"
            ).fetchall()
        }
        assert episode_rows == {
            "profile-salient": ("salient", pytest.approx(9.0)),
            "profile-transient": ("transient", pytest.approx(0.5)),
        }
        node_row = store.connection.execute(
            "SELECT retention_profile, half_life_days FROM nodes WHERE node_id=?",
            ("profile-node",),
        ).fetchone()
        assert node_row is not None
        assert node_row[0] == "stable"
        assert float(node_row[1]) == pytest.approx(365.0)
        assertion_row = store.connection.execute(
            "SELECT retention_profile, half_life_days FROM assertions"
        ).fetchone()
        assert assertion_row is not None
        assert assertion_row[0] == "semantic"
        assert float(assertion_row[1]) == pytest.approx(30.0)


def test_first_projection_evidence_does_not_count_as_relearning() -> None:
    admission_time = _now()
    episode = _episode(
        "initial-projection",
        occurred_at=admission_time - timedelta(days=1),
    )
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        store.record_episode(episode)
        with patch(
            "infrastructure.persistence.memory.sqlite_graph_store.utc_now",
            return_value=admission_time.isoformat(timespec="milliseconds"),
        ):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode.episode_id,
                    nodes=(NodeInput("initial-node", "person", "初始身份"),),
                    aliases=(
                        AliasInput(
                            "initial-node",
                            "初始别名",
                            evidence_id="initial-evidence",
                        ),
                    ),
                    evidence=(
                        EvidenceInput(
                            "initial-evidence",
                            "episode",
                            episode.episode_id,
                            captured_at=episode.occurred_from,
                        ),
                    ),
                )
            )
        row = store.connection.execute(
            "SELECT half_life_days, last_reinforced_at FROM nodes WHERE node_id=?",
            ("initial-node",),
        ).fetchone()
        assert row is not None
        assert float(row[0]) == pytest.approx(30.0)
        assert datetime.fromisoformat(str(row[1])) == admission_time


def test_relation_evidence_does_not_propagate_node_confidence_or_retention() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        episode = _episode("relation-episode")
        store.record_episode(episode)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=episode.episode_id,
                nodes=(
                    NodeInput("owner", "person", "主人"),
                    NodeInput("food", "food", "香菜"),
                ),
                evidence=(
                    EvidenceInput(
                        "relation-evidence",
                        "episode",
                        episode.episode_id,
                        captured_at=episode.occurred_from,
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "likes",
                        object_node_id="food",
                        evidence_ids=("relation-evidence",),
                    ),
                ),
            )
        )
        rows = store.connection.execute(
            "SELECT node_id, confidence, half_life_days FROM nodes ORDER BY node_id"
        ).fetchall()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            ("food", pytest.approx(0.5), pytest.approx(30.0)),
            ("owner", pytest.approx(0.5), pytest.approx(30.0)),
        ]


def test_node_identity_observations_recompute_confidence_and_reinforce_only_that_node() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        first = _episode("identity-episode-1")
        store.record_episode(first)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=first.episode_id,
                nodes=(NodeInput("owner", "person", "主人"),),
                evidence=(
                    EvidenceInput(
                        "identity-evidence-1",
                        "episode",
                        first.episode_id,
                        captured_at=first.occurred_from,
                    ),
                ),
            )
        )
        second = _episode("identity-episode-2")
        store.record_episode(second)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=second.episode_id,
                evidence=(
                    EvidenceInput(
                        "identity-evidence-2",
                        "episode",
                        second.episode_id,
                        captured_at=second.occurred_from,
                    ),
                ),
                aliases=(
                    AliasInput(
                        "owner",
                        "家里的主人",
                        evidence_id="identity-evidence-2",
                    ),
                ),
                mentions=(
                    MentionInput(
                        second.episode_id,
                        "主人",
                        "owner",
                        "resolved",
                        evidence_id="identity-evidence-2",
                    ),
                ),
            )
        )
        row = store.connection.execute(
            "SELECT confidence, half_life_days FROM nodes WHERE node_id='owner'"
        ).fetchone()
        assert row is not None
        assert float(row[0]) == pytest.approx((0.5 + 0.9) / (1.0 + 0.9))
        assert float(row[1]) == pytest.approx(30.0)


def test_importance_events_are_idempotent_and_replayed_from_the_admission_baseline() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        store.upsert_node_record(
            NodeInput("importance-node", "concept", "目标", importance=0.2)
        )
        event = ImportanceEvent(
            event_id="importance-event-1",
            target_kind="node",
            target_id="importance-node",
            direction="raise",
            event_class="meaningful",
            occurred_at=(_now() - timedelta(hours=25)).isoformat(),
        )
        assert store.record_importance_event(event) is True
        assert store.record_importance_event(event) is False
        value = store.connection.execute(
            "SELECT importance FROM nodes WHERE node_id='importance-node'"
        ).fetchone()[0]
        assert float(value) == pytest.approx(0.28)

        lowering = ImportanceEvent(
            event_id="importance-event-2",
            target_kind="node",
            target_id="importance-node",
            direction="lower",
            event_class="major-lower",
            occurred_at=_now().isoformat(),
        )
        assert store.record_importance_event(lowering) is True
        value = store.connection.execute(
            "SELECT importance FROM nodes WHERE node_id='importance-node'"
        ).fetchone()[0]
        assert float(value) == pytest.approx(0.19)


def test_importance_score_control_folds_complete_windows_and_reconciles_late_events() -> (
    None
):
    now = _now()
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        store.upsert_node_record(
            NodeInput("fold-node", "concept", "折叠", importance=0.2)
        )
        old_events = tuple(
            ImportanceEvent(
                event_id=f"fold-event-{days}",
                target_kind="node",
                target_id="fold-node",
                direction="raise",
                event_class="meaningful",
                occurred_at=(now - timedelta(days=days)).isoformat(),
            )
            for days in (5, 3, 1)
        )
        for event in old_events:
            assert store.record_importance_event(event) is True
        expected = MemoryScorePolicy.fold_importance(
            initial=0.2,
            events=old_events,
            target_kind="node",
            target_id="fold-node",
        )
        assert float(
            store.connection.execute(
                "SELECT importance FROM nodes WHERE node_id='fold-node'"
            ).fetchone()[0]
        ) == pytest.approx(expected)

        result = store.compact_score_control(
            now=now.isoformat(), safety_window_days=2.0
        )
        assert result["importance_targets"] == 1
        assert result["importance_events"] == 2
        checkpoint = store.connection.execute(
            """SELECT folded_through, event_count, state_json
                 FROM memory_score_checkpoints
                WHERE target_kind='node' AND target_id='fold-node'
                  AND score_kind='importance'"""
        ).fetchone()
        assert checkpoint is not None
        assert int(checkpoint["event_count"]) == 2
        assert checkpoint["folded_through"] == (now - timedelta(days=3)).isoformat(
            timespec="milliseconds"
        )
        state = json.loads(checkpoint["state_json"])
        assert len(state["folded_event_hash"]) == 64
        assert state["last_event_time"] == checkpoint["folded_through"]

        late = ImportanceEvent(
            event_id="fold-event-late",
            target_kind="node",
            target_id="fold-node",
            direction="raise",
            event_class="core",
            occurred_at=(now - timedelta(days=4)).isoformat(),
        )
        assert store.record_importance_event(late) is False
        assert (
            int(
                store.connection.execute(
                    "SELECT COUNT(*) FROM memory_score_reconciliation "
                    "WHERE target_kind='node' AND target_id='fold-node' "
                    "AND score_kind='importance'"
                ).fetchone()[0]
            )
            == 1
        )
        assert float(
            store.connection.execute(
                "SELECT importance FROM nodes WHERE node_id='fold-node'"
            ).fetchone()[0]
        ) == pytest.approx(expected)


def test_retention_score_control_checkpoint_keeps_hash_and_replay_state() -> None:
    now = _now()
    source_time = now - timedelta(days=10)
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        episode = _episode("retention-fold", occurred_at=source_time)
        store.record_episode(episode)
        for index, days in enumerate((5, 3, 1), start=1):
            assert (
                store.consume_reinforcement_receipt(
                    QualifiedReinforcementReceipt(
                        event_id=f"retention-fold-{index}",
                        target_kind="episode",
                        target_id=episode.episode_id,
                        occurred_at=(now - timedelta(days=days)).isoformat(),
                        outcome_kind="deliberate_review",
                        source_ref=f"review:retention-fold:{index}",
                    )
                )
                is True
            )

        before = float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        )
        result = store.compact_score_control(
            now=now.isoformat(), safety_window_days=2.0
        )
        assert result["retention_targets"] == 1
        assert result["retention_receipts"] == 2
        checkpoint = store.connection.execute(
            """SELECT folded_through, event_count, state_json
                 FROM memory_score_checkpoints
                WHERE target_kind='episode' AND target_id=?
                  AND score_kind='retention'""",
            (episode.episode_id,),
        ).fetchone()
        assert checkpoint is not None
        state = json.loads(checkpoint["state_json"])
        assert int(checkpoint["event_count"]) == 2
        assert len(state["folded_event_hash"]) == 64
        assert state["last_event_time"] == checkpoint["folded_through"]
        assert float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        ) == pytest.approx(before)


def test_qualified_retention_receipts_use_event_time_and_are_idempotent() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        episode = _episode("receipt-episode", occurred_at=_now() - timedelta(hours=1))
        store.record_episode(episode)
        before = float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        )
        receipt = QualifiedReinforcementReceipt(
            event_id="receipt-1",
            target_kind="episode",
            target_id=episode.episode_id,
            occurred_at=_now().isoformat(),
            outcome_kind="action_success",
            source_ref="action:receipt-1",
        )
        assert store.consume_reinforcement_receipt(receipt) is True
        after = float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        )
        assert after > before
        assert store.consume_reinforcement_receipt(receipt) is True
        replay = float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        )
        assert replay == pytest.approx(after)


def test_expired_active_receipt_still_reinforces_with_the_continuous_multiplier() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        episode = _episode("expired-receipt")
        store.record_episode(episode)
        store.connection.execute(
            "UPDATE episodes SET last_reinforced_at=?, next_review_at=? WHERE episode_id=?",
            (
                (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
                "2020",
                episode.episode_id,
            ),
        )
        store.connection.commit()
        receipt = QualifiedReinforcementReceipt(
            event_id="expired-receipt-1",
            target_kind="episode",
            target_id=episode.episode_id,
            occurred_at=_now().isoformat(),
            outcome_kind="deliberate_review",
            source_ref="review:expired",
        )
        assert store.consume_reinforcement_receipt(receipt) is True
        state = store.connection.execute(
            "SELECT half_life_days, state FROM episodes JOIN memory_retention_receipts "
            "ON memory_retention_receipts.target_id=episodes.episode_id "
            "WHERE episodes.episode_id=?",
            (episode.episode_id,),
        ).fetchone()
        assert state is not None
        assert float(state[0]) == pytest.approx(6.0)
    assert state[1] == "accepted"


def test_accepted_active_receipt_survives_archive_before_checkpoint_fold() -> None:
    now = _now()
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        episode = _episode(
            "archive-before-fold",
            occurred_at=now - timedelta(days=10),
        )
        store.record_episode(episode)
        receipt = QualifiedReinforcementReceipt(
            event_id="archive-before-fold-receipt",
            target_kind="episode",
            target_id=episode.episode_id,
            occurred_at=(now - timedelta(days=3)).isoformat(),
            outcome_kind="action_success",
            source_ref="action:archive-before-fold",
        )
        assert store.consume_reinforcement_receipt(receipt) is True
        before = float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        )
        store.connection.execute(
            "UPDATE episodes SET lifecycle='archived' WHERE episode_id=?",
            (episode.episode_id,),
        )
        store.connection.commit()

        assert (
            store.compact_score_control(now=now.isoformat(), safety_window_days=0.0)[
                "retention_receipts"
            ]
            == 1
        )
        after = float(
            store.connection.execute(
                "SELECT half_life_days FROM episodes WHERE episode_id=?",
                (episode.episode_id,),
            ).fetchone()[0]
        )
        assert after == pytest.approx(before)


def test_ignored_receipt_is_not_replayed_if_the_target_later_becomes_active() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        episode = _episode("ignored-replay")
        store.record_episode(episode)
        store.connection.execute(
            "UPDATE episodes SET lifecycle='archived' WHERE episode_id=?",
            (episode.episode_id,),
        )
        store.connection.commit()
        receipt = QualifiedReinforcementReceipt(
            event_id="ignored-replay-receipt",
            target_kind="episode",
            target_id=episode.episode_id,
            occurred_at=_now().isoformat(),
            outcome_kind="deliberate_review",
            source_ref="review:ignored-replay",
        )
        assert store.consume_reinforcement_receipt(receipt) is False
        store.connection.execute(
            "UPDATE episodes SET lifecycle='active' WHERE episode_id=?",
            (episode.episode_id,),
        )
        store.connection.commit()
        assert store.consume_reinforcement_receipt(receipt) is False
        state = store.connection.execute(
            "SELECT state FROM memory_retention_receipts WHERE receipt_id=?",
            (receipt.event_id,),
        ).fetchone()
        assert state is not None and state[0] == "ignored"


def test_authoritative_evidence_relearns_archived_identity_without_multiplier() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        store.upsert_node_record(
            NodeInput(
                "cold-node",
                "concept",
                "冷记忆",
                importance=0.7,
                confidence=0.8,
                retention_profile="semantic",
            )
        )
        assertion_id = store.record_sourced_assertion(
            AssertionInput(
                "cold-node",
                "about",
                object_literal="权威事实",
                assertion_id="cold-assertion",
                importance=0.6,
                confidence=0.8,
                retention_profile="semantic",
            ),
            EvidenceInput("cold-seed", "seed", "cold-source"),
        )
        before = store.connection.execute(
            "SELECT importance, confidence FROM nodes WHERE node_id='cold-node'"
        ).fetchone()
        assertion_before = store.connection.execute(
            "SELECT importance, confidence FROM assertions WHERE assertion_id=?",
            (assertion_id,),
        ).fetchone()
        assert before is not None and assertion_before is not None
        store.connection.execute(
            "UPDATE nodes SET status='archived', half_life_days=2.0, "
            "last_reinforced_at=?, next_review_at=NULL WHERE node_id='cold-node'",
            ((_now() - timedelta(days=10)).isoformat(),),
        )
        store.connection.execute(
            "UPDATE assertions SET lifecycle='archived', half_life_days=2.0, "
            "last_reinforced_at=?, next_review_at=NULL WHERE assertion_id=?",
            ((_now() - timedelta(days=10)).isoformat(), assertion_id),
        )
        store.connection.commit()

        occurred_at = _now()
        assert (
            store.consume_reinforcement_receipt(
                QualifiedReinforcementReceipt(
                    event_id="cold-node-relearn",
                    target_kind="node",
                    target_id="cold-node",
                    occurred_at=occurred_at.isoformat(),
                    outcome_kind="independent_evidence",
                    source_ref="evidence:authoritative-node",
                )
            )
            is True
        )
        assert (
            store.consume_reinforcement_receipt(
                QualifiedReinforcementReceipt(
                    event_id="cold-assertion-relearn",
                    target_kind="assertion",
                    target_id=assertion_id,
                    occurred_at=occurred_at.isoformat(),
                    outcome_kind="independent_evidence",
                    source_ref="evidence:authoritative-assertion",
                )
            )
            is True
        )

        node_row = store.connection.execute(
            "SELECT half_life_days, status, importance, confidence "
            "FROM nodes WHERE node_id='cold-node'"
        ).fetchone()
        assertion_row = store.connection.execute(
            "SELECT half_life_days, lifecycle, importance, confidence "
            "FROM assertions WHERE assertion_id=?",
            (assertion_id,),
        ).fetchone()
        assert node_row is not None and assertion_row is not None
        assert float(node_row[0]) == pytest.approx(30.0)
        assert node_row[1] == "active"
        assert float(node_row[2]) == pytest.approx(float(before[0]))
        assert float(node_row[3]) == pytest.approx(float(before[1]))
        assert float(assertion_row[0]) == pytest.approx(30.0)
        assert assertion_row[1] == "active"
        assert float(assertion_row[2]) == pytest.approx(float(assertion_before[0]))
        assert float(assertion_row[3]) == pytest.approx(float(assertion_before[1]))


def test_memory_use_proposal_requires_the_recall_revision_and_authoritative_outcome() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        memory = MemorySystem(store, elfie_id="elfie-v2")
        episode = _episode("proposal-episode")
        memory.record_closed_episode(episode)
        bundle = memory.recall(RecallRequest(text="proposal-episode"))
        assert bundle.episodes
        proposal = MemoryUseProposal(
            proposal_id="proposal-1",
            recall_revision=bundle.recall_revision,
            occurred_at=_now().isoformat(),
            target_kind="episode",
            target_ids=(episode.episode_id,),
        )
        assert memory.submit_memory_use_proposal(proposal, bundle) is True
        assert memory.submit_memory_use_proposal(proposal, bundle) is False
        receipt = QualifiedReinforcementReceipt(
            event_id="proposal-receipt-1",
            target_kind="episode",
            target_id=episode.episode_id,
            occurred_at=_now().isoformat(),
            outcome_kind="action_success",
            source_ref="action:proposal-1",
            recall_revision=proposal.recall_revision,
            proposal_id=proposal.proposal_id,
        )
        assert memory.consume_reinforcement_receipt(receipt) is True
        with pytest.raises(ValueError, match="stale"):
            memory.submit_memory_use_proposal(
                MemoryUseProposal(
                    proposal_id="proposal-stale",
                    recall_revision=proposal.recall_revision,
                    occurred_at=_now().isoformat(),
                    target_kind="episode",
                    target_ids=(episode.episode_id,),
                ),
                bundle,
            )


def test_genesis_submission_forces_ten_year_retention_for_all_memory_records() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        with store.genesis_submission(
            submission_id="genesis-submission-v2",
            manifest_id="genesis-manifest-v2",
            source_version="canon-v2",
            content_sha256="a" * 64,
            expected_ids=("genesis-episode", "genesis-node", "genesis-evidence"),
            elfie_id="elfie-v2",
        ):
            store.record_episode(
                ClosedEpisode(
                    episode_id="genesis-episode",
                    idempotency_key="genesis-episode-key",
                    occurred_from="2020-01-01T00:00:00+00:00",
                    content_text="Genesis core fact",
                )
            )
            store.upsert_node_record(
                NodeInput(
                    node_id="genesis-node",
                    node_type="knowledge",
                    canonical_label="Genesis core fact",
                    confidence=1.0,
                )
            )
            store.record_sourced_assertion(
                AssertionInput(
                    "genesis-node",
                    "about",
                    object_literal="Genesis core fact",
                    confidence=1.0,
                ),
                EvidenceInput(
                    "genesis-evidence",
                    "seed",
                    "canon-v2#fact-1",
                    excerpt="Genesis core fact",
                ),
            )
        assert store.connection.execute(
            "SELECT half_life_days FROM episodes WHERE episode_id='genesis-episode'"
        ).fetchone()[0] == pytest.approx(3650.0)
        node_row = store.connection.execute(
            "SELECT half_life_days, initial_confidence FROM nodes WHERE node_id='genesis-node'"
        ).fetchone()
        assert node_row is not None
        assert float(node_row[0]) == pytest.approx(3650.0)
        assert float(node_row[1]) == pytest.approx(1.0)
        assertion_row = store.connection.execute(
            "SELECT half_life_days, initial_confidence FROM assertions"
        ).fetchone()
        assert assertion_row is not None
        assert float(assertion_row[0]) == pytest.approx(3650.0)
        assert float(assertion_row[1]) == pytest.approx(1.0)


def test_genesis_seed_evidence_is_admission_prior_not_duplicate_confidence_support() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        with store.genesis_submission(
            submission_id="genesis-confidence-v2",
            manifest_id="genesis-confidence-manifest-v2",
            source_version="canon-v2",
            content_sha256="b" * 64,
            expected_ids=("genesis-confidence-node", "genesis-confidence-evidence"),
            elfie_id="elfie-v2",
        ):
            store.upsert_node_record(
                NodeInput(
                    node_id="genesis-confidence-node",
                    node_type="knowledge",
                    canonical_label="带先验的知识",
                    confidence=0.75,
                )
            )
            store.record_sourced_assertion(
                AssertionInput(
                    "genesis-confidence-node",
                    "about",
                    object_literal="带先验的知识",
                    confidence=0.75,
                ),
                EvidenceInput(
                    "genesis-confidence-evidence",
                    "seed",
                    "canon-v2#confidence",
                    excerpt="带先验的知识",
                ),
            )
        node_confidence = store.connection.execute(
            "SELECT confidence FROM nodes WHERE node_id='genesis-confidence-node'"
        ).fetchone()[0]
        assertion_confidence = store.connection.execute(
            "SELECT confidence FROM assertions"
        ).fetchone()[0]
        assert float(node_confidence) == pytest.approx(0.75)
        assert float(assertion_confidence) == pytest.approx(0.75)


def test_correction_contradicts_old_claim_without_reinforcing_superseded_retention() -> (
    None
):
    now = _now()
    later = now + timedelta(days=3)
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-v2") as store:
        old_episode = _episode(
            "correction-old",
            occurred_at=now - timedelta(days=3),
        )
        new_episode = _episode("correction-new", occurred_at=now)
        store.record_episode(old_episode)
        store.record_episode(new_episode)
        with patch(
            "infrastructure.persistence.memory.sqlite_graph_store.utc_now",
            return_value=now.isoformat(timespec="milliseconds"),
        ):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=old_episode.episode_id,
                    nodes=(NodeInput("correction-owner", "person", "主人"),),
                    evidence=(
                        EvidenceInput(
                            "correction-old-evidence",
                            "episode",
                            old_episode.episode_id,
                            captured_at=old_episode.occurred_from,
                        ),
                    ),
                    assertions=(
                        AssertionInput(
                            "correction-owner",
                            "preferred_name",
                            object_literal="旧名",
                            assertion_id="correction-old-claim",
                            evidence_ids=("correction-old-evidence",),
                        ),
                    ),
                )
            )
        before = store.connection.execute(
            "SELECT confidence, half_life_days FROM assertions "
            "WHERE assertion_id='correction-old-claim'"
        ).fetchone()
        assert before is not None
        with patch(
            "infrastructure.persistence.memory.sqlite_graph_store.utc_now",
            return_value=later.isoformat(timespec="milliseconds"),
        ):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=new_episode.episode_id,
                    evidence=(
                        EvidenceInput(
                            "correction-new-evidence",
                            "episode",
                            new_episode.episode_id,
                            captured_at=later.isoformat(timespec="milliseconds"),
                        ),
                    ),
                    assertions=(
                        AssertionInput(
                            "correction-owner",
                            "preferred_name",
                            object_literal="新名",
                            assertion_id="correction-new-claim",
                            context="correction",
                            supersedes_assertion_id="correction-old-claim",
                            evidence_ids=("correction-new-evidence",),
                        ),
                    ),
                )
            )
        after = store.connection.execute(
            "SELECT confidence, half_life_days, lifecycle, next_review_at "
            "FROM assertions WHERE assertion_id='correction-old-claim'"
        ).fetchone()
        assert after is not None
        assert after[2] == "superseded"
        assert after[3] is None
        assert float(after[0]) < float(before[0])
        assert float(after[1]) == pytest.approx(float(before[1]))
