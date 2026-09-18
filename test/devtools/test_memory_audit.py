"""Focused tests for the read-only Memory audit tool."""

from __future__ import annotations

import csv
import json

from devtools.memory_audit import (
    _read_only_store,
    build_inspection_report,
    build_recall_report,
    write_inspection_bundle,
)
from elfie.brain.memory import (
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
    assert "EVIDENCE:" in report["rendered"]
    assert "claim-1" in report["rendered"]
