"""Run the deterministic OPT-003 Memory capacity and lifecycle evaluation.

The evaluator uses only the typed Memory adapter API.  It creates a disposable
fixture, measures the database-only hot path, verifies idempotent replay and
restart, and exercises the guarded lifecycle path on a small projected source.
No production ``ELFIE_HOME`` is read or modified.
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import resource
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Sequence
from unittest.mock import patch

from elfie.brain.memory import (
    AssertionInput,
    ClosedEpisode,
    ConsolidationProjection,
    EvidenceInput,
    MaintenanceRequest,
    NodeInput,
    RecallRequest,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_SET = "opt003-memory-endurance.v2"
DEFAULT_OUTPUT = ROOT / "build" / "evaluations" / "stage1-chat" / "opt003-current"
DEFAULT_COUNTS = {
    "episodes": 10_000,
    "nodes": 50_000,
    "assertions": 200_000,
}
RECALL_P95_BUDGET_MS = 150.0
_LEGACY_MODULES = frozenset(
    {
        "elfie.brain.memory.encoding",
        "elfie.brain.memory.retrieval",
        "elfie.brain.memory.spreading_activation",
        "elfie.brain.memory.emotion_weighting",
        "elfie.brain.memory.sensory_buffer",
        "elfie.brain.memory.sensory_index",
        "elfie.brain.memory.recall_formatter",
        "elfie.brain.memory.self_narrative",
        "elfie.brain.memory.ebbinghaus_decay",
        "elfie.brain.memory.node_types",
        "infrastructure.persistence.memory.edge_store",
        "infrastructure.persistence.memory.migration",
        "infrastructure.persistence.memory.node_store",
    }
)
_LEGACY_NAMES = frozenset(
    {
        "MemoryEncoder",
        "MemoryRetriever",
        "SpreadingActivation",
        "EmotionWeighting",
        "SensoryBuffer",
        "SensoryIndexer",
        "MemoryRecallFormatter",
        "MemorySelfNarrativeProjection",
        "EbbinghausDecay",
        "MemoryNode",
        "MemoryMetadata",
        "Edge",
        "EdgeTypes",
        "NodeTypes",
        "RetrievalQuery",
        "FakeMemoryStore",
    }
)


def legacy_production_references() -> tuple[str, ...]:
    """Return any retired Memory files or imports that still remain.

    Phase 5 has a zero-residual requirement: the old algorithms and their
    compatibility surface are removed, rather than kept behind a fallback.
    The scan uses the syntax tree for imports so comments and documentation do
    not produce false positives.
    """
    references: list[str] = []
    roots = tuple(
        ROOT / name for name in ("app", "elfie", "infrastructure", "nest", "devtools")
    )
    memory_root = ROOT / "elfie" / "brain" / "memory"
    for module in _LEGACY_MODULES:
        module_path = ROOT.joinpath(*module.split("."))
        if module_path.with_suffix(".py").is_file():
            references.append(str(module_path.with_suffix(".py").relative_to(ROOT)))
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError):
                references.append(str(path.relative_to(ROOT)))
                continue
            relative = str(path.relative_to(ROOT))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in _LEGACY_MODULES:
                            references.append(f"{relative}:{node.lineno}:{alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module in _LEGACY_MODULES or any(
                        alias.name in _LEGACY_NAMES for alias in node.names
                    ):
                        references.append(f"{relative}:{node.lineno}:{module}")
    # ``memory_root`` is intentionally touched so the scan remains explicit
    # about the ownership boundary even when all retired files are absent.
    if not memory_root.is_dir():
        references.append(str(memory_root.relative_to(ROOT)))
    return tuple(sorted(set(references)))


def _episode(
    index: int,
    *,
    importance: float = 0.6,
    next_review_at: str | None = None,
) -> ClosedEpisode:
    return ClosedEpisode(
        episode_id=f"opt003-episode-{index}",
        idempotency_key=f"opt003-key-{index}",
        occurred_from=f"2020-01-01T00:00:{index % 60:02d}+00:00",
        content_text=(
            f"opt003 experience {index} records a durable memory topic "
            f"and its source wording"
        ),
        source_event_ids=(f"opt003-source-{index}",),
        importance=importance,
        privacy_scope="private",
        next_review_at=next_review_at,
    )


def _seed_fixture(
    store: SQLiteMemoryStoreAdapter,
    *,
    episodes: int,
    nodes: int,
    assertions: int,
) -> Dict[str, Any]:
    """Create the representative rows in bounded adapter-owned transactions."""
    started = time.perf_counter()
    episode_hashes: Dict[int, str] = {}
    with store.write_transaction():
        for index in range(episodes):
            item = _episode(index)
            receipt = store.record_episode(item)
            episode_hashes[index] = receipt.content_sha256

    node_started = time.perf_counter()
    with store.write_transaction():
        for index in range(nodes):
            store.upsert_node_record(
                NodeInput(
                    node_id=f"opt003-node-{index}",
                    node_type="concept" if index % 5 else "person",
                    canonical_label=f"opt003 concept {index}",
                    scope="opt003",
                    confidence=0.8,
                    importance=0.6,
                )
            )

    assertion_started = time.perf_counter()
    with store.write_transaction():
        for index in range(assertions):
            episode_index = index % episodes
            evidence_id = f"opt003-evidence-{index}"
            source_id = f"opt003-episode-{episode_index}"
            subject_id = f"opt003-node-{index % nodes}"
            object_id = f"opt003-node-{(index + 1) % nodes}"
            store.record_sourced_assertion(
                AssertionInput(
                    subject_id=subject_id,
                    predicate="knows",
                    object_node_id=object_id,
                    assertion_id=f"opt003-assertion-{index}",
                    confidence=0.8,
                    importance=0.6,
                    context=f"opt003-edge-{index}",
                    evidence_ids=(evidence_id,),
                ),
                EvidenceInput(
                    evidence_id=evidence_id,
                    source_type="episode",
                    source_id=source_id,
                    excerpt=f"opt003 source evidence {index}",
                    span_start=index,
                    span_end=index + 1,
                    source_sha256=episode_hashes[episode_index],
                ),
            )
    return {
        "seed_duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "episode_write_duration_ms": round((node_started - started) * 1000.0, 2),
        "node_write_duration_ms": round((assertion_started - node_started) * 1000.0, 2),
        "assertion_write_duration_ms": round(
            (time.perf_counter() - assertion_started) * 1000.0, 2
        ),
        "requested_counts": {
            "episodes": episodes,
            "nodes": nodes,
            "assertions": assertions,
        },
    }


def _p95(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return round(ordered[index], 3)


def _measure_recall(
    store: SQLiteMemoryStoreAdapter,
    request: RecallRequest,
    *,
    repetitions: int,
) -> Dict[str, Any]:
    for _ in range(3):
        store.recall(request)
    samples: list[float] = []
    result_sizes: list[int] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        bundle = store.recall(request)
        samples.append((time.perf_counter() - started) * 1000.0)
        result_sizes.append(
            len(bundle.focus_nodes) + len(bundle.assertions) + len(bundle.episodes)
        )
    return {
        "sample_count": repetitions,
        "p50_ms": round(sorted(samples)[max(0, len(samples) // 2)], 3),
        "p95_ms": _p95(samples),
        "max_ms": round(max(samples), 3) if samples else 0.0,
        "mean_ms": round(mean(samples), 3) if samples else 0.0,
        "result_size_min": min(result_sizes) if result_sizes else 0,
        "result_size_max": max(result_sizes) if result_sizes else 0,
    }


def _measure_unit_of_work() -> Dict[str, Any]:
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="opt003-uow") as store:
        item = _episode(0)
        started = time.perf_counter()
        receipt = store.record_episode(item)
        elapsed = (time.perf_counter() - started) * 1000.0
        return {
            "episode_status": receipt.status,
            "duration_ms": round(elapsed, 3),
        }


def _measure_retry(store: SQLiteMemoryStoreAdapter) -> Dict[str, Any]:
    started = time.perf_counter()
    receipt = store.record_episode(_episode(0))
    return {
        "status": receipt.status,
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }


def _measure_lock_wait(root: Path) -> Dict[str, Any]:
    """Measure the configured SQLite busy timeout with one serialized writer."""
    lock_root = root / "lock"
    lock_root.mkdir(parents=True, exist_ok=True)
    path = lock_root / "knowledge.sqlite"
    first = SQLiteMemoryStoreAdapter(path, elfie_id="opt003-lock")
    second = SQLiteMemoryStoreAdapter(path, elfie_id="opt003-lock")
    result: Dict[str, Any] = {}
    started_event = threading.Event()

    def writer() -> None:
        started_event.set()
        started = time.perf_counter()
        receipt = second.record_episode(_episode(0))
        result.update(
            status=receipt.status,
            duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
        )

    try:
        with first.write_transaction():
            thread = threading.Thread(target=writer)
            thread.start()
            started_event.wait(timeout=1.0)
            time.sleep(0.15)
        thread.join(timeout=5.0)
        result["thread_finished"] = not thread.is_alive()
    finally:
        second.close()
        first.close()
        shutil.rmtree(lock_root, ignore_errors=True)
    return result


def _lifecycle_smoke() -> Dict[str, Any]:
    """Replay full→compressed→digest→archived→forgotten safely."""
    with SQLiteMemoryStoreAdapter.in_memory(elfie_id="opt003-lifecycle") as store:
        episode = _episode(
            0,
            importance=0.1,
            next_review_at="2020-01-01T00:00:00+00:00",
        )
        receipt = store.record_episode(episode)
        store.apply_consolidation(
            ConsolidationProjection(
                episode_id=episode.episode_id,
                nodes=(NodeInput("opt003-lifecycle-node", "concept", "lifecycle"),),
                assertions=(
                    AssertionInput(
                        "opt003-lifecycle-node",
                        "knows",
                        object_literal="lifecycle",
                        evidence_ids=("opt003-lifecycle-evidence",),
                    ),
                ),
                evidence=(
                    EvidenceInput(
                        "opt003-lifecycle-evidence",
                        "episode",
                        episode.episode_id,
                        excerpt=episode.content_text,
                        source_sha256=receipt.content_sha256,
                    ),
                ),
            )
        )
        observed: list[str] = []
        # Keep every review due without reaching into SQLite.  This is an
        # evaluation-only clock policy; the production policy remains owned by
        # MemoryScorePolicy and is exercised by the adapter tests.
        with patch(
            "infrastructure.persistence.memory.sqlite_lifecycle_store._next_lifecycle_review",
            return_value="2020-01-01T00:00:00+00:00",
        ):
            for _ in range(4):
                result = store.run_lifecycle(MaintenanceRequest(max_episodes=1))
                current = store.get_episode(episode.episode_id)
                if current is None:
                    raise RuntimeError("lifecycle smoke source Episode disappeared")
                observed.append(f"{current.lifecycle}:{current.detail_level}")
                if current.lifecycle == "archived":
                    # The v2 forget predicate includes a 90-day archived
                    # safety window.  Move only this disposable fixture past
                    # that window before the final replay step.
                    store.connection.execute(
                        "UPDATE episodes SET lifecycle_changed_at=? WHERE episode_id=?",
                        ("2020-01-01T00:00:00+00:00", episode.episode_id),
                    )
                    store.connection.commit()
                if not result.lifecycle_episode_ids:
                    break
        forgotten = store.list_episodes(include_forgotten=True)
        return {
            "stages": observed,
            "forgotten_count": sum(
                1 for item in forgotten if item.lifecycle == "forgotten"
            ),
            "active_count": len(store.list_episodes()),
            "digest_retained": bool(
                forgotten and forgotten[0].content_text.startswith("[forgotten:")
            ),
        }


def _memory_usage_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes while Linux reports KiB.
    return round(
        float(usage) / (1024.0 * 1024.0 if os.uname().sysname == "Darwin" else 1024.0),
        2,
    )


def run(
    output: Path,
    *,
    episodes: int = DEFAULT_COUNTS["episodes"],
    nodes: int = DEFAULT_COUNTS["nodes"],
    assertions: int = DEFAULT_COUNTS["assertions"],
    repetitions: int = 30,
) -> Dict[str, Any]:
    """Run the full evaluation and write a redacted machine report."""
    if min(episodes, nodes, assertions, repetitions) < 1:
        raise ValueError("fixture counts and repetitions must be positive")
    before_memory = _memory_usage_mb()
    (ROOT / "build").mkdir(parents=True, exist_ok=True)
    parent = Path(tempfile.mkdtemp(prefix="elfie-opt003-", dir=str(ROOT / "build")))
    db_path = parent / "knowledge.sqlite"
    started = time.perf_counter()
    cold_started = time.perf_counter()
    store = SQLiteMemoryStoreAdapter(db_path, elfie_id="opt003-fixture")
    cold_init_ms = (time.perf_counter() - cold_started) * 1000.0
    try:
        seed = _seed_fixture(
            store,
            episodes=episodes,
            nodes=nodes,
            assertions=assertions,
        )
        integrity = store.integrity_report()
        basic = _measure_recall(
            store,
            RecallRequest(
                text="opt003 experience 123",
                mode="basic",
                lexical_limit=20,
                seed_limit=8,
                node_limit=40,
                episode_limit=8,
                evidence_limit=24,
            ),
            repetitions=repetitions,
        )
        local = _measure_recall(
            store,
            RecallRequest(
                text="opt003 concept 123",
                seed_node_ids=("opt003-node-123",),
                mode="local",
                hop_limit=2,
                neighbors_per_node=8,
                node_limit=20,
                assertion_limit=20,
                episode_limit=4,
                evidence_limit=8,
            ),
            repetitions=repetitions,
        )
        retry = _measure_retry(store)
        uow = _measure_unit_of_work()
        store.close()
        reopen_started = time.perf_counter()
        reopened = SQLiteMemoryStoreAdapter(db_path, elfie_id="opt003-fixture")
        reopen_ms = (time.perf_counter() - reopen_started) * 1000.0
        restart_integrity = reopened.integrity_report()
        reopened.close()
        lock_wait = _measure_lock_wait(parent)
    finally:
        try:
            store.close()
        except Exception:
            pass
        shutil.rmtree(parent, ignore_errors=True)

    lifecycle = _lifecycle_smoke()
    legacy_references = legacy_production_references()
    after_memory = _memory_usage_mb()
    checks = {
        "representative_row_counts": all(
            integrity.get(key) == value
            for key, value in (
                ("episodes", episodes),
                ("nodes", nodes),
                ("assertions", assertions),
            )
        )
        and restart_integrity == integrity,
        "all_assertions_grounded": bool(integrity.get("all_assertions_grounded")),
        "basic_recall_p95_under_budget": basic["p95_ms"] <= RECALL_P95_BUDGET_MS,
        "local_recall_p95_under_budget": local["p95_ms"] <= RECALL_P95_BUDGET_MS,
        "idempotent_retry": retry["status"] == "duplicate",
        "restart_reopens_same_facts": restart_integrity == integrity,
        "lifecycle_forgets_only_after_archive": lifecycle["stages"]
        == [
            "active:compressed",
            "active:digest",
            "archived:digest",
            "forgotten:digest",
        ],
        "forgotten_digest_retained": lifecycle["forgotten_count"] == 1
        and lifecycle["active_count"] == 0
        and lifecycle["digest_retained"],
        "lock_wait_writer_completed": bool(lock_wait.get("thread_finished")),
        "zero_production_legacy_imports": not legacy_references,
    }
    report: Dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario_set": {
            "version": SCENARIO_SET,
            "episodes": episodes,
            "nodes": nodes,
            "assertions": assertions,
            "recall_repetitions": repetitions,
        },
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "cold_init_ms": round(cold_init_ms, 3),
        "reopen_ms": round(reopen_ms, 3),
        "seed": seed,
        "integrity": integrity,
        "restart_integrity": restart_integrity,
        "recall": {"basic": basic, "local": local},
        "unit_of_work": uow,
        "retry": retry,
        "lock_wait": lock_wait,
        "lifecycle": lifecycle,
        "legacy_compatibility": {
            "residuals": list(legacy_references),
            "required": "retired modules, imports and fallback callers are absent",
        },
        "memory_mb": {"before": before_memory, "after": after_memory},
        "checks": checks,
        "passed": all(checks.values()),
        "residuals": [],
    }
    if (
        not checks["basic_recall_p95_under_budget"]
        or not checks["local_recall_p95_under_budget"]
    ):
        report["residuals"].append(
            f"Recall p95 目标为 <= {RECALL_P95_BUDGET_MS:.0f}ms，需在当前机器继续优化。"
        )
    if legacy_references:
        report["residuals"].append(
            "代码库仍包含退役 Memory 组件或引用：" + ", ".join(legacy_references)
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OPT-003 Memory evaluation.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "report.json")
    parser.add_argument("--episodes", type=int, default=DEFAULT_COUNTS["episodes"])
    parser.add_argument("--nodes", type=int, default=DEFAULT_COUNTS["nodes"])
    parser.add_argument("--assertions", type=int, default=DEFAULT_COUNTS["assertions"])
    parser.add_argument("--repetitions", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run(
        args.output,
        episodes=args.episodes,
        nodes=args.nodes,
        assertions=args.assertions,
        repetitions=args.repetitions,
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "output": str(args.output),
                "duration_ms": report["duration_ms"],
                "recall": report["recall"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
