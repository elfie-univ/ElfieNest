"""Deterministic OPT-001 E2/E3 gates for the typed Canon/Genesis path."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Iterable

from app.features.adoption import AcceptedAdoptionReservation
from elfie.brain.memory.memory_records import RecallRequest
from elfie.profile import configure_species_catalog
from infrastructure.persistence.configuration.species import load_species_catalog
from infrastructure.persistence.configuration.world import load_world_canon
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED_STAGES = ("youth", "young_adult", "mature", "elder")
SEEDS = (11, 23, 47)


def _published_species() -> tuple[str, ...]:
    catalog = load_species_catalog()
    return tuple(
        definition.species_id
        for definition in catalog.definitions
        if definition.status == "published"
    )


def _reservation(elfie_id: str, species_id: str, seed: int, stage: str):
    return AcceptedAdoptionReservation(
        elfie_id=elfie_id,
        owner_user_id=1,
        name=f"E2E3-{species_id}-{stage}-{seed}",
        species_id=species_id,
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=seed,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2001-01-01",
        age_months={"youth": 36, "young_adult": 96, "mature": 156, "elder": 216}[stage],
        life_stage=stage,
    )


def _query_variants(fact: Any) -> Iterable[str]:
    yield fact.statement
    for term in fact.retrieval_terms[:2]:
        yield term
    for term in fact.aliases[:2]:
        yield term


def _eligible_for_species(fact: Any, species_id: str) -> bool:
    eligibility = set(getattr(fact, "eligibility", ()))
    return "all" in eligibility or species_id in eligibility


def _query_cases_for_species(
    facts: Iterable[Any], species_id: str, limit: int = 96
) -> list[tuple[Any, str]]:
    """Build a bounded E2 set that covers every eligible fact first."""
    eligible = [
        fact
        for fact in facts
        if getattr(fact, "status", None) == "active"
        and _eligible_for_species(fact, species_id)
    ]
    variants = [tuple(_query_variants(fact)) for fact in eligible]
    cases: list[tuple[Any, str]] = []
    for variant_index in range(max((len(item) for item in variants), default=0)):
        for fact, fact_variants in zip(eligible, variants):
            if variant_index >= len(fact_variants):
                continue
            cases.append((fact, fact_variants[variant_index]))
            if len(cases) >= limit:
                return cases
    return cases


def _contains_fact(bundle: Any, fact_id: str) -> bool:
    needle = f":{''.join(char if char.isalnum() or char in '-_' else '-' for char in fact_id)}"
    return any(needle in node.node_id for node in bundle.focus_nodes) or any(
        needle in assertion.subject_id
        or (assertion.object_node_id is not None and needle in assertion.object_node_id)
        for assertion in bundle.assertions
    )


def run(output: Path) -> dict[str, Any]:
    world = load_world_canon()
    configure_species_catalog(load_species_catalog())
    species_ids = _published_species()
    if not species_ids:
        raise RuntimeError("没有 published 物种，不能运行 OPT-001 E2/E3")

    unknown_facts = tuple(
        fact for fact in world.knowledge if fact.status == "unknown-boundary"
    )
    e2_total = 0
    e2_hits = 0
    unknown_total = 0
    unknown_hits = 0
    e3_total = 0
    e3_passed = 0
    failures: list[str] = []

    with tempfile.TemporaryDirectory(
        prefix="elfie-opt001-e2e3-", dir="/private/tmp"
    ) as raw_root:
        root = Path(raw_root)
        for species_index, species_id in enumerate(species_ids):
            query_cases = _query_cases_for_species(world.knowledge, species_id)
            if len(query_cases) < 96:
                raise RuntimeError(
                    f"物种 {species_id} 的 E2 题目不足 96 条：{len(query_cases)}"
                )
            for stage_index, stage in enumerate(PUBLISHED_STAGES):
                for seed in SEEDS:
                    e3_total += 1
                    elfie_id = f"{species_index + 1:02d}{stage_index + 1:02d}{seed:04d}"
                    adapter = FinalElfieWorkspaceAdapter(root)
                    reservation = _reservation(elfie_id, species_id, seed, stage)
                    workspace = Path(adapter.materialize(reservation))
                    memory_path = workspace / "memory" / "knowledge.sqlite"
                    try:
                        with SQLiteMemoryStoreAdapter(memory_path) as storage:
                            episode_count = storage.count_episodes()
                            person_count = storage.count_graph_nodes("person")
                            marker = storage.get_graph_node(
                                f"genesis:manifest:{elfie_id}"
                            )
                            valid_graph = (
                                episode_count == 5
                                and person_count == 13
                                and marker is not None
                            )
                            if not valid_graph:
                                failures.append(f"E3:{species_id}:{stage}:{seed}:graph")
                            for fact, query in query_cases:
                                e2_total += 1
                                bundle = storage.recall(
                                    RecallRequest(
                                        text=query,
                                        lexical_limit=20,
                                        node_limit=40,
                                        assertion_limit=80,
                                        episode_limit=8,
                                        evidence_limit=24,
                                    )
                                )
                                if _contains_fact(bundle, fact.fact_id):
                                    e2_hits += 1
                                elif len(failures) < 40:
                                    failures.append(
                                        f"E2:{species_id}:{fact.fact_id}:{query}"
                                    )
                            for fact in unknown_facts:
                                unknown_total += 1
                                bundle = storage.recall(
                                    RecallRequest(
                                        text=fact.retrieval_terms[0],
                                        lexical_limit=20,
                                        node_limit=40,
                                        assertion_limit=80,
                                        episode_limit=8,
                                        evidence_limit=24,
                                    )
                                )
                                if any(
                                    assertion.predicate == "knows_boundary"
                                    and assertion.qualifiers.get("epistemic_status")
                                    == "uncertain"
                                    for assertion in bundle.assertions
                                ):
                                    unknown_hits += 1
                                elif len(failures) < 40:
                                    failures.append(
                                        f"E2:unknown:{species_id}:{fact.fact_id}"
                                    )
                            with SQLiteMemoryStoreAdapter(memory_path) as reopened:
                                restart_ok = (
                                    reopened.count_episodes() == 5
                                    and reopened.get_graph_node(
                                        f"genesis:manifest:{elfie_id}"
                                    )
                                    is not None
                                )
                            if not restart_ok:
                                failures.append(
                                    f"E3:{species_id}:{stage}:{seed}:restart"
                                )
                            if valid_graph and restart_ok:
                                e3_passed += 1
                    finally:
                        adapter.release(elfie_id)

    e2_rate = e2_hits / e2_total if e2_total else 0.0
    unknown_rate = unknown_hits / unknown_total if unknown_total else 0.0
    e3_rate = e3_passed / e3_total if e3_total else 0.0
    report = {
        "schema_version": "opt001-e2e3.v1",
        "canon_version": world.canon_version,
        "published_species": list(species_ids),
        "e2": {
            "queries": e2_total,
            "hits": e2_hits,
            "rate": e2_rate,
            "passed": e2_rate >= 0.95,
            "unknown_queries": unknown_total,
            "unknown_hits": unknown_hits,
            "unknown_rate": unknown_rate,
            "unknown_passed": unknown_rate >= 0.95,
        },
        "e3": {
            "combinations": e3_total,
            "passed": e3_passed,
            "rate": e3_rate,
            "passed_gate": e3_rate == 1.0,
        },
        "failures": failures,
        "passed": e2_rate >= 0.95 and unknown_rate >= 0.95 and e3_rate == 1.0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic OPT-001 E2/E3 gates"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build/evaluations/stage1-chat/opt001-e2e3/report.json",
    )
    args = parser.parse_args()
    report = run(args.output)
    print(
        json.dumps(
            {"passed": report["passed"], "report": str(args.output)}, ensure_ascii=False
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
