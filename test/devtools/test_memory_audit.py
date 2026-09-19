"""Focused tests for the read-only Memory audit tool."""

from __future__ import annotations

import csv
import json

import pytest

from devtools.memory_audit import (
    MemoryInspectionStaleError,
    _read_only_store,
    build_add_episode_preview,
    build_inspection_report,
    build_recall_report,
    write_inspection_bundle,
)
from elfie.brain.memory import (
    AliasInput,
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    NodeInput,
    RecallRequest,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def _seed_graph(store: SQLiteMemoryStoreAdapter) -> None:
    owner = {"elfie_id": "elfie-a"}
    store.upsert_node_record(
        NodeInput(
            "elfie",
            "elfie",
            "艾菲",
            description="当前精灵",
            properties=dict(owner),
        )
    )
    store.upsert_node_record(
        NodeInput(
            "person-1",
            "person",
            "小林",
            description="朋友",
            confidence=0.4,
            properties=dict(owner),
        )
    )
    store.upsert_node_record(
        NodeInput(
            "knowledge-1",
            "knowledge",
            "喜欢散步",
            description="一条知识",
            properties=dict(owner),
        )
    )
    store.record_sourced_assertion(
        AssertionInput(
            subject_id="elfie",
            predicate="knows",
            object_node_id="knowledge-1",
            evidence_ids=("evidence-1",),
            assertion_id="assertion-1",
        ),
        EvidenceInput(
            evidence_id="evidence-1",
            source_type="seed",
            source_id="seed-1",
            excerpt="艾菲知道自己喜欢散步。",
        ),
    )
    store.record_sourced_assertion(
        AssertionInput(
            subject_id="elfie",
            predicate="relationship",
            object_node_id="person-1",
            evidence_ids=("evidence-2",),
            assertion_id="assertion-2",
        ),
        EvidenceInput(
            evidence_id="evidence-2",
            source_type="seed",
            source_id="seed-1",
            excerpt="艾菲认识小林。",
        ),
    )


def _seed_direct_node_evidence(store: SQLiteMemoryStoreAdapter) -> None:
    store.record_episode(
        ClosedEpisode(
            "episode-direct-evidence",
            "episode-direct-evidence-key",
            "2026-09-05T00:00:00+00:00",
            "小林也叫小林同学。",
        )
    )
    store.apply_consolidation(
        ConsolidationProjection(
            episode_id="episode-direct-evidence",
            evidence=(
                EvidenceInput(
                    "evidence-node-direct",
                    "episode",
                    "episode-direct-evidence",
                    excerpt="小林也叫小林同学。",
                ),
            ),
            aliases=(
                AliasInput(
                    node_id="person-1",
                    alias="小林同学",
                    evidence_id="evidence-node-direct",
                ),
            ),
        )
    )


def _seed_other_elfie(store: SQLiteMemoryStoreAdapter) -> None:
    store.upsert_node_record(
        NodeInput(
            "other-elfie",
            "elfie",
            "另一只精灵",
            properties={"elfie_id": "elfie-b"},
        )
    )
    store.upsert_node_record(
        NodeInput(
            "other-knowledge",
            "knowledge",
            "另一条知识",
            properties={"elfie_id": "elfie-b"},
        )
    )
    store.record_sourced_assertion(
        AssertionInput(
            subject_id="other-elfie",
            predicate="knows",
            object_node_id="other-knowledge",
            evidence_ids=("evidence-other-elfie",),
            assertion_id="assertion-other-elfie",
        ),
        EvidenceInput(
            "evidence-other-elfie",
            "seed",
            "other-seed",
            excerpt="另一只精灵知道另一条知识。",
        ),
    )


def test_inspection_filter_keeps_one_hop_graph_context() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        _seed_graph(store)

        report = build_inspection_report(
            store,
            database="memory.sqlite",
            node_types=("person",),
        )

    assert report["counts"]["focus_nodes"] == 1
    assert set(report["focus_node_ids"]) == {"person-1"}
    assert {node["node_id"] for node in report["data"]["nodes"]} == {
        "elfie",
        "person-1",
    }
    assert [item["predicate"] for item in report["data"]["assertions"]] == [
        "relationship"
    ]
    assert report["checks"]["assertions_without_evidence"] == []


def test_inspection_distinguishes_total_counts_from_bounded_loaded_counts() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        _seed_graph(store)
        report = build_inspection_report(store, database="memory.sqlite", limit=1)

    assert report["counts"]["nodes"] == 3
    assert report["loaded_counts"]["nodes"] == 1
    assert report["coverage"]["status"] == "partial"
    assert report["coverage"]["truncated"]["nodes"] is True
    assert report["snapshot"]["coverage"] == "partial"


def test_inspection_counts_share_scope_and_keep_direct_evidence_visible() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        _seed_graph(store)
        _seed_direct_node_evidence(store)
        report = build_inspection_report(store, database="memory.sqlite", limit=1)

        assert report["counts"]["nodes"] == len(store.list_graph_nodes(limit=1000))
        assert report["counts"]["assertions"] == len(
            store.list_graph_assertions(limit=1000)
        )
        assert report["counts"]["evidence"] == len(
            store.list_memory_evidence(limit=1000)
        )

    assert report["counts"]["evidence"] == 3
    assert report["loaded_counts"]["evidence"] == 1
    assert report["coverage"]["truncated"]["evidence"] is True
    assert report["coverage"]["status"] == "partial"
    assert report["matched_counts"]["nodes"] == 3
    assert report["matched_counts"]["assertions"] == 2
    assert {item["evidence_id"] for item in report["data"]["evidence"]} == {
        "evidence-1",
    }


def test_empty_inspection_is_complete_zero_state_not_read_failure() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-empty") as store:
        report = build_inspection_report(store, database="memory.sqlite")

    assert report["coverage"]["status"] == "complete"
    assert report["counts"]["episodes"] == 0
    assert report["counts"]["nodes"] == 0
    assert report["counts"]["assertions"] == 0
    assert report["counts"]["evidence"] == 0
    assert all(
        not report["data"][key]
        for key in ("episodes", "nodes", "assertions", "evidence")
    )


def test_inspection_scope_excludes_other_elfie_and_includes_superseded_claims(
    tmp_path,
) -> None:
    database = tmp_path / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(database, elfie_id="elfie-a") as store:
        _seed_graph(store)
        store.record_episode(
            ClosedEpisode(
                "episode-old-claim",
                "episode-old-claim-key",
                "2026-09-06T00:00:00+00:00",
                "我叫小林。",
            )
        )
        store.record_episode(
            ClosedEpisode(
                "episode-new-claim",
                "episode-new-claim-key",
                "2026-09-07T00:00:00+00:00",
                "我叫小周。",
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-old-claim",
                evidence=(
                    EvidenceInput("evidence-old-claim", "episode", "episode-old-claim"),
                ),
                nodes=(NodeInput("owner-a", "person", "主人"),),
                assertions=(
                    AssertionInput(
                        "owner-a",
                        "preferred_name",
                        object_literal="小林",
                        evidence_ids=("evidence-old-claim",),
                        assertion_id="claim-old",
                    ),
                ),
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-new-claim",
                evidence=(
                    EvidenceInput("evidence-new-claim", "episode", "episode-new-claim"),
                ),
                assertions=(
                    AssertionInput(
                        "owner-a",
                        "preferred_name",
                        object_literal="小周",
                        evidence_ids=("evidence-new-claim",),
                        assertion_id="claim-new",
                        supersedes_assertion_id="claim-old",
                    ),
                ),
            )
        )

    with SQLiteMemoryStoreAdapter(database, elfie_id="elfie-b") as store:
        _seed_other_elfie(store)

    with SQLiteMemoryStoreAdapter(database, elfie_id="elfie-a") as store:
        report = build_inspection_report(store, database="memory.sqlite")
        assertion_ids = {item["assertion_id"] for item in report["data"]["assertions"]}
        node_ids = {item["node_id"] for item in report["data"]["nodes"]}

    assert {"claim-old", "claim-new"}.issubset(assertion_ids)
    assert "assertion-other-elfie" not in assertion_ids
    assert "other-elfie" not in node_ids
    assert report["counts"]["assertions"] == len(report["data"]["assertions"])


def test_inspection_cursor_pages_large_graph_without_dangling_edges() -> None:
    node_count = 1105
    assertion_count = node_count - 1
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-large") as store:
        store.record_episode(
            ClosedEpisode(
                "episode-large",
                "episode-large-key",
                "2026-09-08T00:00:00+00:00",
                "大库分页夹具。",
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-large",
                nodes=tuple(
                    NodeInput(
                        f"large-node-{index:04d}",
                        "knowledge",
                        f"分页知识 {index}",
                    )
                    for index in range(node_count)
                ),
                evidence=tuple(
                    EvidenceInput(
                        f"large-evidence-{index:04d}",
                        "episode",
                        "episode-large",
                        excerpt=f"分页证据 {index}",
                    )
                    for index in range(1, node_count)
                ),
                assertions=tuple(
                    AssertionInput(
                        "large-node-0000",
                        "related_to",
                        object_node_id=f"large-node-{index:04d}",
                        evidence_ids=(f"large-evidence-{index:04d}",),
                        assertion_id=f"large-assertion-{index:04d}",
                    )
                    for index in range(1, node_count)
                ),
            )
        )

        cursor = None
        seen_nodes: set[str] = set()
        seen_assertions: set[str] = set()
        seen_evidence: set[str] = set()
        page_count = 0
        while True:
            report = build_inspection_report(
                store,
                database="memory.sqlite",
                limit=256,
                cursor=cursor,
            )
            page_count += 1
            page_nodes = {
                item["node_id"]
                for item in (
                    report["data"]["nodes"] + report["data"].get("context_nodes", [])
                )
            }
            for item in report["data"]["assertions"]:
                assert item["subject_id"] in page_nodes
                assert item["object_node_id"] in page_nodes
            node_ids = {item["node_id"] for item in report["data"]["nodes"]}
            assertion_ids = {
                item["assertion_id"] for item in report["data"]["assertions"]
            }
            evidence_ids = {item["evidence_id"] for item in report["data"]["evidence"]}
            assert not seen_nodes.intersection(node_ids)
            assert not seen_assertions.intersection(assertion_ids)
            assert not seen_evidence.intersection(evidence_ids)
            seen_nodes.update(node_ids)
            seen_assertions.update(assertion_ids)
            seen_evidence.update(evidence_ids)
            cursor = report["pagination"]["next_cursor"]
            if cursor is None:
                break

    assert page_count > 1
    assert len(seen_nodes) == node_count
    assert len(seen_assertions) == assertion_count
    assert len(seen_evidence) == assertion_count
    assert report["counts"]["nodes"] == node_count
    assert report["counts"]["assertions"] == assertion_count
    assert report["counts"]["evidence"] == assertion_count
    assert report["coverage"]["status"] == "complete"


def test_inspection_cursor_rejects_mixed_consistency_and_marks_revision_unavailable() -> (
    None
):
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        _seed_graph(store)
        first = build_inspection_report(store, database="memory.sqlite", limit=1)
        assert first["snapshot"]["semantic_revision"] is None
        assert first["snapshot"]["semantic_revision_status"] == "unavailable"
        cursor = first["pagination"]["next_cursor"]
        assert cursor

        store.upsert_node_record(NodeInput("stale-node", "knowledge", "读中发生的变化"))

        with pytest.raises(MemoryInspectionStaleError):
            build_inspection_report(
                store,
                database="memory.sqlite",
                limit=1,
                cursor=cursor,
            )


def test_inspection_bundle_exports_external_graph_files(tmp_path) -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        _seed_graph(store)
        report = build_inspection_report(store, database="memory.sqlite")

    output_dir = write_inspection_bundle(report, tmp_path / "audit")
    expected = {
        "report.json",
        "nodes.csv",
        "edges.csv",
        "episodes.csv",
        "evidence.csv",
        "graph.cypher",
        "README.txt",
    }
    assert {path.name for path in output_dir.iterdir()} == expected
    with (output_dir / "nodes.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["id"] for row in rows} == {"elfie", "person-1", "knowledge-1"}
    assert "MERGE (n:MemoryNode" in (output_dir / "graph.cypher").read_text(
        encoding="utf-8"
    )
    loaded = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert loaded["format"] == "elfienest.memory-audit.v1"


def test_read_only_snapshot_does_not_write_source_database(tmp_path) -> None:
    database = tmp_path / "knowledge.sqlite"
    with SQLiteMemoryStoreAdapter(database) as store:
        _seed_graph(store)
    before = database.read_bytes()

    with _read_only_store(database) as store:
        assert store.integrity_report()["all_assertions_grounded"] is True

    assert database.read_bytes() == before


def test_recall_report_keeps_paths_and_evidence() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        store.record_episode(
            ClosedEpisode(
                "episode-1",
                "episode-key-1",
                "2026-09-04T00:00:00+00:00",
                "主人喜欢香菜。",
            )
        )
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id="episode-1",
                nodes=(
                    NodeInput("owner", "person", "主人"),
                    NodeInput("food", "food", "香菜"),
                ),
                evidence=(
                    EvidenceInput(
                        "episode-evidence",
                        "episode",
                        "episode-1",
                        excerpt="主人喜欢香菜。",
                    ),
                ),
                assertions=(
                    AssertionInput(
                        "owner",
                        "likes",
                        object_node_id="food",
                        evidence_ids=("episode-evidence",),
                        assertion_id="claim-1",
                    ),
                ),
            )
        )

        report = build_recall_report(
            store,
            RecallRequest(text="香菜", mode="basic_local"),
        )

    assert report["counts"]["focus_nodes"] >= 1
    assert report["counts"]["evidence"] >= 1
    assert report["snapshot"]["consistency"] == "single_request"
    assert report["selection"]["candidate_boundary"] == "scored_candidates_only"
    assert report["selection"]["candidates"]
    assert report["selection"]["summaries"]
    assert any(
        item["candidate_id"] in {"owner", "food", "episode-1"}
        for item in report["selection"]["candidates"]
    )
    assert "EVIDENCE:" in report["rendered"]
    assert "claim-1" in report["rendered"]


def test_add_episode_preview_runs_real_chain_and_reports_diff() -> None:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="elfie-a") as store:
        report = build_add_episode_preview(
            store,
            content_text="主人喜欢香菜，今天在花园散步。",
        )

    assert report["operation"]["status"] == "completed"
    assert report["operation"]["sandbox"] is True
    assert report["operation"]["production_mutated"] is False
    assert report["before"]["counts"]["episodes"] == 0
    assert report["after"]["counts"]["episodes"] == 1
    assert report["changes"]["added_ids"]["episodes"]
    assert report["changes"]["added_ids"]["evidence"]
    assert report["receipt"]["consolidation"]["consolidated_episode_ids"]
