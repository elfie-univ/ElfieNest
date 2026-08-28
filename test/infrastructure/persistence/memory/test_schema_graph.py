"""Target graph, evidence and source-preservation contract tests."""

from __future__ import annotations

import sqlite3

import pytest

from elfie.brain.memory.memory_records import (
    AssertionEvidenceInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    MentionInput,
    NodeInput,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def _projection(store: SQLiteMemoryStoreAdapter) -> None:
    store.record_episode(
        ClosedEpisode(
            episode_id="episode-1",
            idempotency_key="turn-1",
            occurred_from="2026-08-01T00:00:00+00:00",
            content_text="主人喜欢香菜。",
        )
    )
    store.apply_consolidation(
        ConsolidationProjection(
            episode_id="episode-1",
            nodes=(
                NodeInput("owner", "person", "主人"),
                NodeInput("food", "food", "香菜"),
            ),
            mentions=(MentionInput("episode-1", "主人", "owner", "resolved"),),
            evidence=(
                EvidenceInput("ev-1", "episode", "episode-1", excerpt="主人喜欢香菜。"),
            ),
            assertions=(
                AssertionInput(
                    "owner",
                    "likes",
                    object_node_id="food",
                    confidence=0.9,
                    support_score=0.9,
                    evidence_ids=("ev-1",),
                    assertion_id="claim-1",
                ),
            ),
            assertion_evidence=(AssertionEvidenceInput("claim-1", "ev-1"),),
        )
    )


def test_assertions_require_nodes_and_are_not_bare_triples() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        _projection(store)
        with pytest.raises(sqlite3.IntegrityError):
            store.connection.execute(
                """INSERT INTO assertions(
                    assertion_id,subject_node_id,predicate,object_node_id,
                    fingerprint,created_at,updated_at
                ) VALUES ('dangling','missing','knows','food','x','now','now')"""
            )
        store.connection.rollback()
        # A different viewpoint/polarity is a distinct qualified claim.
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                evidence=(
                    EvidenceInput("ev-2", "episode", "episode-1", excerpt="另一种看法"),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "likes",
                        object_node_id="food",
                        polarity="negative",
                        viewpoint="reported",
                        conflict_group="likes-owner-food",
                        evidence_ids=("ev-2",),
                        assertion_id="claim-2",
                    ),
                ),
            )
        )
        rows = store.connection.execute("SELECT COUNT(*) FROM assertions").fetchone()
        assert rows[0] == 2


def test_evidence_and_mentions_round_trip_and_graph_edges_are_derived() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        _projection(store)
        assertion = store.graph_assertions_for(("owner",))[0]
        assert assertion.evidence_ids == ("ev-1",)
        assert store.get_assertion_evidence(("claim-1",))[0].source_id == "episode-1"
        assert store.get_edges("owner")[0].target == "food"
        assert store.get_node("episode-1").metadata["consolidated"] is True


def test_invalid_episode_evidence_rolls_back_entire_projection() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        store.record_episode(ClosedEpisode("episode-1", "k", "2026", "完整内容"))
        with pytest.raises(ValueError):
            store.apply_consolidation(
                ConsolidationProjection(
                    episode_id="episode-1",
                    nodes=(NodeInput("n", "concept", "会回滚"),),
                    evidence=(
                        EvidenceInput("bad", "episode", "other", excerpt="错误来源"),
                    ),
                )
            )
        assert store.get_graph_node("n") is None
        assert (
            store.connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        )


def test_target_has_rebuildable_text_projections_not_legacy_tables() -> None:
    with SQLiteMemoryStoreAdapter.in_memory() as store:
        tables = {
            row["name"]
            for row in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"episodes", "nodes", "assertions", "evidence"}.issubset(tables)
        assert {"episodes_fts", "nodes_fts"}.issubset(tables)
        assert not tables.intersection(
            {"entities", "entity_edges", "people", "events", "memory_notes"}
        )
