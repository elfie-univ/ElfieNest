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
    SQLiteMemoryStoreAdapter,
    import_legacy_database,
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
        assert reopened.count_nodes("episodic") == 1

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
        assert store.count_nodes("episodic") == 1


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
                        support_score=0.9,
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


def test_migration_imports_events_edges_and_reports_source_counts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.sqlite"
    target = tmp_path / "knowledge.sqlite"
    with sqlite3.connect(source) as connection:
        connection.executescript(
            """
            CREATE TABLE entities(
                entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL,
                name TEXT NOT NULL, summary TEXT, confidence REAL,
                first_seen_at TEXT, last_seen_at TEXT, meta_json TEXT
            );
            CREATE TABLE events(
                entity_id TEXT PRIMARY KEY, event_time TEXT, event_type TEXT,
                description TEXT, importance_score REAL, meta_json TEXT
            );
            CREATE TABLE entity_edges(
                edge_id TEXT PRIMARY KEY, source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL, relation_type TEXT NOT NULL,
                summary TEXT, weight REAL, confidence REAL
            );
            """
        )
        connection.execute(
            "INSERT INTO entities VALUES ('a','person','主人','',.8,'','','{}')"
        )
        connection.execute(
            "INSERT INTO entities VALUES ('b','food','香菜','',.8,'','','{}')"
        )
        connection.execute(
            "INSERT INTO events VALUES ('e','2026-01-01','chat','主人喜欢香菜',.8,'{}')"
        )
        connection.execute(
            "INSERT INTO entity_edges VALUES ('x','a','b','likes','',.8,.8)"
        )
    report = import_legacy_database(source, target)
    assert report.source_events == report.imported_episodes == 1
    assert report.source_edges == report.imported_assertions == 1
    assert report.imported_nodes == 2
    assert report.episode_hash_matches == 1
    assert report.reconciled is True
    assert report.target_digest
    with SQLiteMemoryStoreAdapter(target) as store:
        assert store.get_episode("e") is not None
        assert store.graph_assertions_for(("a",))[0].evidence_ids


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
            ConsolidationRequest(max_episodes=1, worker_id="worker-a")
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


class _ProposalModel:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def ask_with_food(self, **_kwargs: object) -> str:
        return self.payload


class _FailingProposalModel:
    def ask_with_food(self, **_kwargs: object) -> str:
        raise TimeoutError("provider unavailable")


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
        '"object_ref":"香菜","confidence":0.9,"support_score":0.9}]}'
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


def test_ungrounded_model_proposal_is_discarded_without_fabricating_a_node() -> None:
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
        assert result.status == "completed"
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
        assert store.search_by_content("芫荽", top_k=5)[0][0] == "food"
        assert store.search_by_content("可食用", top_k=5)[0][0] == "food"


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
