from pathlib import Path

from devtools.evals.opt001_e2e3 import run


def test_opt001_e2_e3_deterministic_gates_pass(tmp_path: Path) -> None:
    report = run(tmp_path / "opt001-e2e3.json")

    assert report["passed"] is True
    assert report["published_species"] == ["fox", "dog"]
    assert report["e2"]["rate"] >= 0.95
    assert report["e2"]["unknown_rate"] >= 0.95
    assert report["e3"]["passed_gate"] is True
