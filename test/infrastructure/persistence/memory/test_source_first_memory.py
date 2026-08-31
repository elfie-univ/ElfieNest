"""Replayable gates for the source-first Memory implementation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from elfie.brain.memory.candidates import EpisodicMemoryCandidate
from elfie.brain.memory.consolidation import MemoryConsolidator
from elfie.brain.memory.memory_records import (
    AliasInput,
    AssertionEvidenceInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    ConsolidationRequest,
    DescriptionInput,
    EvidenceInput,
    MentionInput,
    NodeInput,
    RecallRequest,
)
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.memory.recall_renderer import render_recall_bundle
from elfie.message_types import EventId
from infrastructure.persistence.memory import (
    EpisodeIdempotencyError,
    MemoryStoreResetRequired,
    MemoryStoreSchemaError,
    SQLiteMemoryStoreAdapter,
)


def test_episode_write_is_complete_idempotent_and_reopenable(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite"
    episode = ClosedEpisode(
        episode_id="episode-1",
        idempotency_key="source-turn-1",
        occurred_from="2026-08-26T01:02:03+00:00",
        content_text="我第一次学到精灵星球的重力。",
        source_event_ids=("event-1",),
        media_refs=(),
        metadata={"emotion": "惊喜", "topic": "gravity"},
    )
    with SQLiteMemoryStoreAdapter(path) as store:
        first = store.record_episode(episode)
        duplicate = store.record_episode(episode)
        assert first.status == "committed"
        assert duplicate.status == "duplicate"
        assert store.get_episode("episode-1").content_text == episode.content_text
        assert (
            store.connection.execute(
                "SELECT content_sha256 FROM episodes WHERE episode_id='episode-1'"
            ).fetchone()[0]
            == first.content_sha256
        )
    with SQLiteMemoryStoreAdapter(path) as reopened:
        assert reopened.get_episode("episode-1").content_text == episode.content_text
        assert reopened.count_episodes() == 1

    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(episode)
        with pytest.raises(EpisodeIdempotencyError):
            store.record_episode(
                ClosedEpisode(
                    episode_id="episode-other",
                    idempotency_key="source-turn-1",
                    occurred_from=episode.occurred_from,
                    content_text="不同内容",
                )
            )


def test_completed_candidate_uses_source_first_episode_even_at_low_intensity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    candidate = EpisodicMemoryCandidate(
        candidate_id=EventId("memory-interaction:receipt-1"),
        base_revision=0,
        content="主人问候我，我完成了回复。",
        emotion="calm",
        intensity=0.0,
        stimulus="completed-owner-interaction:conversation-1",
        source_event_ids=(EventId("owner-1"), EventId("reply-1"), EventId("receipt-1")),
        created_at=datetime(2026, 8, 26, 1, 2, 3, tzinfo=timezone.utc),
    )
    with SQLiteMemoryStoreAdapter(path) as store:
        memory = MemorySystem(store)
        receipt = memory.commit_episode_candidate(candidate)
        assert receipt.status.value == "committed"
        row = store.connection.execute(
            "SELECT content_text, consolidation_state, source_event_ids_json FROM episodes"
        ).fetchone()
        assert row[0] == candidate.content
        assert row[1] == "pending"
        assert "owner-1" in row[2]
    with SQLiteMemoryStoreAdapter(path) as store:
        restarted = MemorySystem(store)
        duplicate = restarted.commit_episode_candidate(candidate)
        assert duplicate.status.value == "duplicate"
        assert store.count_episodes() == 1


def test_consolidation_is_source_grounded_and_retrieval_is_hybrid() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode(
                "episode-1",
                "k1",
                "2026-08-26T00:00:00+00:00",
                "主人喜欢香菜，香菜也叫芫荽。",
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(
                    NodeInput("owner", "person", "主人"),
                    NodeInput("coriander", "food", "香菜"),
                ),
                aliases=(AliasInput("coriander", "芫荽", evidence_id="ev-1"),),
                evidence=(
                    EvidenceInput(
                        "ev-1", "episode", "episode-1", excerpt="主人喜欢香菜"
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "likes",
                        object_node_id="coriander",
                        importance=0.9,
                        evidence_ids=("ev-1",),
                        assertion_id="claim-1",
                    ),
                ),
            )
        )
        bundle = store.recall(
            RecallRequest(text="芫荽", hop_limit=1, character_limit=1000)
        )
        assert bundle.episodes[0].episode_id == "episode-1"
        assert bundle.assertions[0].evidence_ids == ("ev-1",)
        assert bundle.evidence[0].source_id == "episode-1"
        assert len(bundle.episodes[0].excerpt) <= 1000


def test_legacy_or_mixed_store_requires_explicit_reset_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE entities(entity_id TEXT PRIMARY KEY, name TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO entities VALUES ('legacy-1', '旧记录')")
        connection.commit()

    with pytest.raises(MemoryStoreResetRequired, match="back it up and rebuild"):
        SQLiteMemoryStoreAdapter(path)

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT name FROM entities").fetchone()[0] == "旧记录"


def test_unsupported_version_requires_explicit_fresh_store(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=4")
        connection.commit()

    with pytest.raises(
        MemoryStoreSchemaError, match="unsupported Memory schema version"
    ):
        SQLiteMemoryStoreAdapter(path)


def test_projection_reuses_unambiguous_semantic_identity_across_episodes() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        for index, content in enumerate(("主人喜欢香菜", "主人又提到芫荽"), start=1):
            store.record_episode(
                ClosedEpisode(
                    episode_id=f"episode-{index}",
                    idempotency_key=f"key-{index}",
                    occurred_from=f"2026-08-{index:02d}",
                    content_text=content,
                )
            )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(NodeInput("food-1", "food", "香菜"),),
                evidence=(
                    EvidenceInput(
                        "evidence-1", "episode", "episode-1", excerpt="主人喜欢香菜"
                    ),
                ),
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-2",
                nodes=(NodeInput("food-2", "food", "香菜"),),
                aliases=(AliasInput("food-2", "芫荽", evidence_id="evidence-2"),),
                evidence=(
                    EvidenceInput(
                        "evidence-2", "episode", "episode-2", excerpt="主人又提到芫荽"
                    ),
                ),
            )
        )
        rows = store.connection.execute(
            "SELECT node_id FROM nodes WHERE node_type='food' AND canonical_label='香菜'"
        ).fetchall()
        assert [row[0] for row in rows] == ["food-1"]
        assert store.find_graph_nodes("芫荽")[0].node_id == "food-1"


def test_alias_resolution_keeps_the_existing_canonical_label() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k1", "2026-01-01", "香菜资料"))
        store.record_episode(ClosedEpisode("episode-2", "k2", "2026-01-02", "芫荽资料"))
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(NodeInput("food-1", "food", "香菜"),),
                aliases=(AliasInput("food-1", "芫荽", evidence_id="ev-1"),),
                evidence=(
                    EvidenceInput("ev-1", "episode", "episode-1", excerpt="香菜资料"),
                ),
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-2",
                nodes=(NodeInput("food-2", "food", "芫荽"),),
                aliases=(AliasInput("food-2", "芫荽", evidence_id="ev-2"),),
                evidence=(
                    EvidenceInput("ev-2", "episode", "episode-2", excerpt="芫荽资料"),
                ),
            )
        )
        row = store.connection.execute(
            "SELECT node_id, canonical_label FROM nodes WHERE node_type='food' AND merged_into IS NULL"
        ).fetchone()
        assert tuple(row) == ("food-1", "香菜")
        assert store.find_graph_nodes("芫荽")[0].label == "香菜"


def test_projection_rejects_cross_episode_mentions_and_preserves_stance_conflicts() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k1", "2026-01-01", "甲"))
        store.record_episode(ClosedEpisode("episode-2", "k2", "2026-01-02", "乙"))
        with pytest.raises(ValueError, match="projected Episode"):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id="episode-1",
                    nodes=(NodeInput("a", "person", "甲"),),
                    mentions=(MentionInput("episode-2", "甲", "a", "resolved"),),
                    evidence=(
                        EvidenceInput("ev-1", "episode", "episode-1", excerpt="甲"),
                    ),
                )
            )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(NodeInput("a", "person", "甲"),),
                evidence=(EvidenceInput("ev-1", "episode", "episode-1", excerpt="甲"),),
                assertions=(
                    AssertionInput(
                        "a",
                        "is",
                        object_literal="甲",
                        evidence_ids=("ev-1",),
                        assertion_id="claim-1",
                    ),
                ),
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                evidence=(EvidenceInput("ev-1", "episode", "episode-1", excerpt="甲"),),
                assertions=(
                    AssertionInput(
                        "a",
                        "is",
                        object_literal="甲",
                        evidence_ids=("ev-1",),
                        assertion_id="claim-1",
                    ),
                ),
                assertion_evidence=(
                    AssertionEvidenceInput("claim-1", "ev-1", stance="contradicts"),
                ),
            )
        )
        assert (
            store.connection.execute(
                "SELECT stance FROM assertion_evidence WHERE assertion_id='claim-1' AND evidence_id='ev-1'"
            ).fetchone()[0]
            == "context"
        )


def test_merge_retargets_mentions_and_folds_qualified_assertions() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k1", "2026-01-01", "甲和乙"))
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(NodeInput("a", "person", "甲"), NodeInput("b", "person", "乙")),
                mentions=(
                    # Keep the mention on the source identity so the merge can
                    # prove that historical rows are retargeted.
                    MentionInput("episode-1", "甲", "a", "resolved"),
                ),
                evidence=(
                    EvidenceInput("ev", "episode", "episode-1", excerpt="甲和乙"),
                ),
                assertions=(
                    AssertionInput(
                        "a",
                        "knows",
                        object_node_id="b",
                        evidence_ids=("ev",),
                        assertion_id="claim",
                    ),
                ),
            )
        )
        assert store.merge_graph_nodes("a", "b") is True
        assert store.resolve_graph_node_id("a") == "b"
        assert (
            store.connection.execute(
                "SELECT node_id FROM episode_mentions WHERE episode_id='episode-1'"
            ).fetchone()[0]
            == "b"
        )
        assert store.graph_assertions_for(("b",))[0].subject_id == "b"
        assert store.find_graph_nodes("甲")[0].node_id == "b"


def test_claim_and_retry_batch_keep_source_episode_on_failure() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k1", "2026-01-01", "包含香菜"))
        consolidator = MemoryConsolidator(store)
        receipt = consolidator.run_batch(
            ConsolidationRequest(max_episodes=1, worker_id="worker-a"),
            model_port=_ProposalModel('{"nodes":[],"mentions":[],"assertions":[]}'),
        )
        assert receipt.status == "completed"
        assert receipt.consolidated_episode_ids == ("episode-1",)
        assert store.get_episode("episode-1").content_text == "包含香菜"
        assert (
            store.connection.execute(
                "SELECT consolidation_state FROM episodes WHERE episode_id='episode-1'"
            ).fetchone()[0]
            == "consolidated"
        )


def test_source_first_consolidation_without_model_stays_retryable() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-no-model", "k-no-model", "2026-01-01", "包含香菜")
        )
        receipt = MemoryConsolidator(store).run_batch(
            ConsolidationRequest(max_episodes=1)
        )

        assert receipt.status == "failed"
        assert receipt.failed_episode_ids == ("episode-no-model",)
        assert store.get_episode("episode-no-model").content_text == "包含香菜"
        assert store.connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0] == 0
        assert (
            store.connection.execute(
                "SELECT consolidation_state FROM episodes WHERE episode_id='episode-no-model'"
            ).fetchone()[0]
            == "failed"
        )


def test_source_first_invalid_model_proposal_stays_retryable() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode(
                "episode-invalid-model", "k-invalid-model", "2026-01-01", "包含香菜"
            )
        )
        receipt = MemoryConsolidator(store).run_batch(
            ConsolidationRequest(max_episodes=1),
            model_port=_ProposalModel(
                '{"nodes":[{"label":"火星"}],"mentions":[],"assertions":[]}'
            ),
        )

        assert receipt.status == "failed"
        assert receipt.failed_episode_ids == ("episode-invalid-model",)
        assert not store.find_graph_nodes("火星")


def test_expired_lease_is_reclaimable_and_failure_is_scheduled() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k1", "2026-01-01", "内容"))
        claimed = store.claim_episodes(limit=1, owner="dead-worker", lease_seconds=1)
        assert claimed
        store.connection.execute(
            "UPDATE episodes SET lease_until='1970-01-01T00:00:00+00:00' WHERE episode_id='episode-1'"
        )
        store.connection.commit()
        assert store.recover_expired_leases() == 1
        assert store.mark_episode_failed("episode-1", "temporary") is True
        row = store.connection.execute(
            "SELECT consolidation_state, next_attempt_at, metadata_json FROM episodes WHERE episode_id='episode-1'"
        ).fetchone()
        assert row[0] == "failed"
        assert row[1]
        assert "temporary" in row[2]


def test_stale_consolidation_claim_cannot_publish_or_fail_an_episode() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        source = ClosedEpisode("episode-fenced", "fenced-key", "2026-01-01", "内容")
        store.record_episode(source)
        first = store.claim_episodes(limit=1, owner="worker-a", lease_seconds=1)[0]
        assert first.metadata["_memory_claim_owner"] == "worker-a"
        assert first.metadata["_memory_claim_attempt"] == 1

        store.connection.execute(
            "UPDATE episodes SET lease_until='1970-01-01T00:00:00+00:00' "
            "WHERE episode_id=?",
            (source.episode_id,),
        )
        store.connection.commit()
        assert store.recover_expired_leases() == 1
        second = store.claim_episodes(limit=1, owner="worker-b", lease_seconds=120)[0]
        assert second.metadata["_memory_claim_attempt"] == 2
        stored = store.get_episode(source.episode_id)

        with pytest.raises(ValueError, match="stale consolidation claim"):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=source.episode_id,
                    nodes=(NodeInput("fenced-node", "concept", "内容"),),
                    evidence=(
                        EvidenceInput(
                            "fenced-evidence",
                            "episode",
                            source.episode_id,
                            excerpt=source.content_text,
                            source_sha256=stored.content_sha256,
                        ),
                    ),
                    claim_owner=str(first.metadata["_memory_claim_owner"]),
                    claim_attempt=int(first.metadata["_memory_claim_attempt"]),
                )
            )
        assert (
            store.mark_episode_failed(
                source.episode_id,
                "stale worker",
                owner="worker-a",
                attempt=1,
            )
            is False
        )
        assert store.connection.execute(
            "SELECT consolidation_state, lease_owner, consolidation_attempts "
            "FROM episodes WHERE episode_id=?",
            (source.episode_id,),
        ).fetchone()[:2] == ("processing", "worker-b")


class _ProposalModel:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def ask_with_food(self, **_kwargs: object) -> str:
        return self.payload


class _FailingProposalModel:
    def ask_with_food(self, **_kwargs: object) -> str:
        raise TimeoutError("provider unavailable")


class _NameCorrectionModel:
    def ask_with_food(self, **kwargs: object) -> str:
        prompt = str(kwargs.get("prompt", ""))
        name = "小周" if "小周" in prompt else "小林"
        context = "correction" if name == "小周" else "owner_claim"
        return (
            '{"nodes":[{"label":"我","type":"person"}],'
            '"mentions":[{"surface_text":"我","label":"我"}],'
            '"assertions":[{"subject_ref":"我","predicate":"preferred_name",'
            f'"object_literal":"{name}","context":"{context}",'
            '"epistemic_status":"reported","confidence":0.95,'
            '"importance_event":"major"}]}'
        )


def test_model_failure_keeps_episode_retryable_and_source_intact() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode(
                "episode-model-failure", "model-failure", "2026-01-01", "我叫小林"
            )
        )
        result = MemoryConsolidator(store).run_batch(
            ConsolidationRequest(max_episodes=1), model_port=_FailingProposalModel()
        )
        assert result.status == "failed"
        assert store.get_episode("episode-model-failure").content_text == "我叫小林"
        row = store.connection.execute(
            "SELECT consolidation_state FROM episodes WHERE episode_id=?",
            ("episode-model-failure",),
        ).fetchone()
        assert row[0] == "failed"


def test_model_projection_is_grounded_and_uses_global_semantic_ids() -> None:
    proposal = (
        '{"nodes":[{"label":"主人","type":"person"},'
        '{"label":"香菜","type":"food","aliases":["芫荽"]}],'
        '"mentions":[{"surface_text":"主人","label":"主人"},'
        '{"surface_text":"香菜","label":"香菜"}],'
        '"assertions":[{"subject_ref":"主人","predicate":"likes",'
        '"object_ref":"香菜","confidence":0.9,"importance_event":"major"}]}'
    )
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-1", "k1", "2026-01-01", "主人喜欢香菜，也叫芫荽")
        )
        result = MemoryConsolidator(store).run_batch(
            ConsolidationRequest(max_episodes=1), model_port=_ProposalModel(proposal)
        )
        assert result.status == "completed"
        assert store.find_graph_nodes("芫荽")[0].label == "香菜"
        claim = store.graph_assertions_for(
            (store.find_graph_nodes("主人")[0].node_id,)
        )[0]
        assert claim.predicate == "likes"
        assert claim.evidence_ids


def test_ungrounded_model_proposal_is_retryable_without_fabricating_a_node() -> None:
    proposal = (
        '{"nodes":[{"label":"火星","type":"place"}],"mentions":[],"assertions":[]}'
    )
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-1", "k1", "2026-01-01", "我看到了花园")
        )
        result = MemoryConsolidator(store).run_batch(
            ConsolidationRequest(max_episodes=1), model_port=_ProposalModel(proposal)
        )
        assert result.status == "failed"
        assert result.failed_episode_ids == ("episode-1",)
        assert not store.find_graph_nodes("火星")


def test_recall_respects_graph_limits_and_renderer_preserves_provenance() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode(
                "episode-1",
                "k1",
                "2026-01-01",
                "主人喜欢香菜。" + "细节" * 200,
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(
                    NodeInput("owner", "person", "主人"),
                    NodeInput("food", "food", "香菜"),
                    NodeInput("meal", "concept", "晚餐"),
                ),
                mentions=(MentionInput("episode-1", "主人", "owner", "resolved"),),
                evidence=(
                    EvidenceInput(
                        "ev-1", "episode", "episode-1", excerpt="主人喜欢香菜。"
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "likes",
                        object_node_id="food",
                        evidence_ids=("ev-1",),
                        assertion_id="a-1",
                    ),
                    AssertionInput(
                        "food",
                        "used_in",
                        object_node_id="meal",
                        evidence_ids=("ev-1",),
                        assertion_id="a-2",
                    ),
                ),
            )
        )
        bundle = store.recall(
            RecallRequest(
                text="主人",
                hop_limit=2,
                node_limit=2,
                assertion_limit=1,
                episode_limit=1,
                evidence_limit=1,
                character_limit=120,
            )
        )
        assert len(bundle.focus_nodes) <= 2
        assert len(bundle.assertions) <= 1
        assert len(bundle.episodes) <= 1
        assert bundle.limits.truncated is True

        rendered = render_recall_bundle(bundle, character_limit=120)
        assert len(rendered) <= 120
        assert rendered.startswith("[MEMORY_DATA]")
        assert rendered.endswith("[/MEMORY_DATA]")
        assert "episode-1" in rendered or "a-1" in rendered or len(bundle.episodes) == 0


def test_recall_can_start_from_a_seed_and_filter_relation_and_node_type() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-1", "k1", "2026-01-01", "主人认识小狐")
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(
                    NodeInput("owner", "person", "主人"),
                    NodeInput("fox", "animal", "小狐"),
                ),
                evidence=(
                    EvidenceInput(
                        "ev-1", "episode", "episode-1", excerpt="主人认识小狐"
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "knows",
                        object_node_id="fox",
                        evidence_ids=("ev-1",),
                        assertion_id="knows",
                    ),
                ),
            )
        )
        bundle = store.recall(
            RecallRequest(
                seed_node_ids=("owner",),
                node_types=("animal",),
                relation_types=("knows",),
                mode="local",
                hop_limit=1,
            )
        )
        assert [node.label for node in bundle.focus_nodes] == ["小狐"]
        assert [assertion.predicate for assertion in bundle.assertions] == ["knows"]


def test_rebuild_indexes_recreates_alias_and_description_search_text() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k1", "2026-01-01", "香菜资料"))
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(NodeInput("food", "food", "香菜"),),
                aliases=(AliasInput("food", "芫荽", evidence_id="ev"),),
                descriptions=(
                    DescriptionInput("food", "一种可食用的香草", evidence_id="ev"),
                ),
                evidence=(
                    EvidenceInput("ev", "episode", "episode-1", excerpt="香菜资料"),
                ),
            )
        )
        store.rebuild_text_indexes()
        assert store.search_text("芫荽", top_k=5)[0][0] == "food"
        assert store.search_text("可食用", top_k=5)[0][0] == "food"


def test_recall_prioritizes_a_direct_label_over_broad_distractors() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        for index in range(20):
            store.upsert_node_record(
                NodeInput(
                    node_id=f"distractor-{index:02d}",
                    node_type="event",
                    canonical_label=f"普通事件 {index}",
                    description="这段经历提到了迷雾镇，但不是区域定义。",
                )
            )
        store.upsert_node_record(
            NodeInput(
                node_id="known-region",
                node_type="knowledge",
                canonical_label="当前可确认的生活区域是迷雾镇（Mistyville）。",
                description="迷雾镇是这只 Elfie 已知的生活区域。",
            )
        )

        bundle = store.recall(
            RecallRequest(text="迷雾镇", lexical_limit=20, seed_limit=8)
        )

        assert any(node.node_id == "known-region" for node in bundle.focus_nodes)


def test_conflicting_qualified_claims_remain_visible_with_their_sources() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-1", "k1", "2026-01-01", "主人喜欢香菜")
        )
        store.record_episode(
            ClosedEpisode("episode-2", "k2", "2026-01-02", "主人不喜欢香菜")
        )
        for episode_id, evidence_id, polarity, text in (
            ("episode-1", "ev-1", "positive", "主人喜欢香菜"),
            ("episode-2", "ev-2", "negative", "主人不喜欢香菜"),
        ):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(
                        NodeInput("owner", "person", "主人"),
                        NodeInput("food", "food", "香菜"),
                    ),
                    evidence=(
                        EvidenceInput(evidence_id, "episode", episode_id, excerpt=text),
                    ),
                    assertions=(
                        AssertionInput(
                            "owner",
                            "likes",
                            object_node_id="food",
                            polarity=polarity,
                            evidence_ids=(evidence_id,),
                        ),
                    ),
                )
            )
        bundle = store.recall(RecallRequest(seed_node_ids=("owner",), mode="basic"))
        assert {item.qualifiers["polarity"] for item in bundle.assertions} == {
            "positive",
            "negative",
        }
        assert len(bundle.conflicts) == 1
        assert {item.source_id for item in bundle.evidence} == {
            "episode-1",
            "episode-2",
        }


def test_seed_graph_recall_honors_episode_time_window() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        for episode_id, day, person in (
            ("episode-old", "2026-01-01", "甲"),
            ("episode-new", "2026-02-01", "乙"),
        ):
            store.record_episode(
                ClosedEpisode(episode_id, episode_id, day, f"主人认识{person}")
            )
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id=episode_id,
                    nodes=(
                        NodeInput("owner", "person", "主人"),
                        NodeInput(f"person-{person}", "person", person),
                    ),
                    evidence=(
                        EvidenceInput(
                            f"evidence-{person}",
                            "episode",
                            episode_id,
                            excerpt=f"主人认识{person}",
                        ),
                    ),
                    assertions=(
                        AssertionInput(
                            "owner",
                            "knows",
                            object_node_id=f"person-{person}",
                            evidence_ids=(f"evidence-{person}",),
                        ),
                    ),
                )
            )
        bundle = store.recall(
            RecallRequest(
                seed_node_ids=("owner",),
                mode="basic",
                occurred_from="2026-01-15",
                occurred_to="2026-02-15",
            )
        )
        assert [assertion.object_node_id for assertion in bundle.assertions] == [
            "person-乙"
        ]


def test_correction_supersedes_active_assertion_and_preserves_old_evidence() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-old", "old", "2026-01-01", "我叫小林")
        )
        store.record_episode(
            ClosedEpisode("episode-new", "new", "2026-01-02", "我不叫小林，我叫小周")
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-old",
                nodes=(NodeInput("owner", "person", "主人"),),
                evidence=(
                    EvidenceInput(
                        "ev-old", "episode", "episode-old", excerpt="我叫小林"
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "preferred_name",
                        object_literal="小林",
                        evidence_ids=("ev-old",),
                        assertion_id="claim-old",
                    ),
                ),
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-new",
                nodes=(NodeInput("owner", "person", "主人"),),
                evidence=(
                    EvidenceInput(
                        "ev-new",
                        "episode",
                        "episode-new",
                        excerpt="我不叫小林，我叫小周",
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "preferred_name",
                        object_literal="小周",
                        evidence_ids=("ev-new",),
                        assertion_id="claim-new",
                        supersedes_assertion_id="claim-old",
                    ),
                ),
            )
        )
        rows = store.connection.execute(
            "SELECT assertion_id, lifecycle, supersedes_assertion_id FROM assertions ORDER BY assertion_id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("claim-new", "active", "claim-old"),
            ("claim-old", "superseded", None),
        ]
        bundle = store.recall(
            RecallRequest(seed_node_ids=("owner",), mode="basic", assertion_limit=8)
        )
        assert any(item.assertion_id == "claim-new" for item in bundle.assertions)


def test_natural_name_correction_forms_a_supersedes_chain() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(
            ClosedEpisode("episode-name-old", "name-old", "2026-01-01", "我叫小林")
        )
        store.record_episode(
            ClosedEpisode(
                "episode-name-new",
                "name-new",
                "2026-01-02",
                "我不叫小林了，叫小周。",
            )
        )
        consolidator = MemoryConsolidator(store)
        assert (
            consolidator.run_batch(
                ConsolidationRequest(max_episodes=1), model_port=_NameCorrectionModel()
            ).status
            == "completed"
        )
        assert (
            consolidator.run_batch(
                ConsolidationRequest(max_episodes=1), model_port=_NameCorrectionModel()
            ).status
            == "completed"
        )

        rows = store.connection.execute(
            """SELECT assertion_id, object_literal_json, lifecycle, supersedes_assertion_id
                 FROM assertions
                WHERE predicate='preferred_name'
                ORDER BY assertion_id"""
        ).fetchall()
        assert len(rows) == 2
        old = next(row for row in rows if row[1] == '"小林"')
        new = next(row for row in rows if row[1] == '"小周"')
        assert old[1:] == ('"小林"', "superseded", None)
        assert new[1:] == ('"小周"', "active", old[0])
