from pathlib import Path

from devtools.evals.opt002_continuous_learning import run


def test_opt002_continuous_learning_machine_gate_passes(tmp_path: Path) -> None:
    report = run(tmp_path / "opt002-report.json")

    assert report["scenario_set"] == {
        "version": "opt002-continuous-learning.v1",
        "scenario_count": 8,
    }
    assert report["machine_gate_passed"] is True
    assert report["passed"] is True
    assert all(item["passed"] is True for item in report["results"])
