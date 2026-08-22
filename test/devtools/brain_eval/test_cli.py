from __future__ import annotations

import json
from pathlib import Path

import devtools.__main__ as developer_main


def test_unified_cli_lists_the_versioned_scenario_catalog(capsys) -> None:
    exit_code = developer_main.main(["brain-eval", "catalog", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(payload) == 24
    assert payload[0]["family_id"] == "p0-response-scope"


def test_unified_cli_returns_invalid_without_a_traceback(
    tmp_path: Path,
    capsys,
) -> None:
    missing = tmp_path / "missing.json"

    exit_code = developer_main.main(
        [
            "brain-eval",
            "capture",
            "--candidate",
            str(missing),
            "--fixture",
            str(missing),
            "--scenario",
            str(missing),
            "--run-id",
            "invalid-input",
        ]
    )

    assert exit_code == 2
    assert "invalid CandidateSpec file" in capsys.readouterr().err
