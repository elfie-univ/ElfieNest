from pathlib import Path

from devtools.evals.opt003_memory_endurance import (
    legacy_production_references,
    run,
)


def test_no_production_caller_imports_legacy_memory_stack() -> None:
    assert legacy_production_references() == ()


def test_opt003_memory_endurance_smoke_gate_passes(tmp_path: Path) -> None:
    report = run(
        tmp_path / "opt003-report.json",
        episodes=12,
        nodes=24,
        assertions=48,
        repetitions=5,
    )

    assert report["scenario_set"]["version"] == "opt003-memory-endurance.v2"
    assert report["scenario_set"]["episodes"] == 12
    assert report["scenario_set"]["nodes"] == 24
    assert report["scenario_set"]["assertions"] == 48
    assert report["passed"] is True
    assert all(report["checks"].values())
    assert report["integrity"]["all_assertions_grounded"] is True
