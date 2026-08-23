"""Tests for the historical Python quality-debt baseline gate."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.quality.checks.python_baseline import (
    DiagnosticDelta,
    compare_diagnostics,
    format_gate_summary,
    parse_mypy_output,
    parse_ruff_format_output,
    parse_ruff_output,
    quality_exit_code,
)


def test_ruff_parser_does_not_retain_diagnostic_message_secrets(
    tmp_path: Path,
) -> None:
    # Given
    secret_marker = "TOP_SECRET_TEST_VALUE"
    output = json.dumps(
        [
            {
                "code": "F841",
                "filename": str(tmp_path / "sample.py"),
                "location": {"row": 3, "column": 5},
                "message": f"unused value {secret_marker}",
            }
        ]
    )

    # When
    diagnostics = parse_ruff_output(output, tmp_path)

    # Then
    assert sum(diagnostics.values()) == 1
    assert secret_marker not in "".join(diagnostics)
    assert next(iter(diagnostics)).startswith("sample.py:F841:")


def test_mypy_parser_does_not_retain_diagnostic_message_secrets(
    tmp_path: Path,
) -> None:
    # Given
    secret_marker = "TOP_SECRET_TEST_VALUE"
    output = json.dumps(
        {
            "file": str(tmp_path / "sample.py"),
            "line": 8,
            "column": 2,
            "message": f"incompatible value {secret_marker}",
            "code": "assignment",
            "severity": "error",
        }
    )

    # When
    diagnostics = parse_mypy_output(output, tmp_path)

    # Then
    assert sum(diagnostics.values()) == 1
    assert secret_marker not in "".join(diagnostics)
    assert next(iter(diagnostics)).startswith("sample.py:assignment:")


def test_mypy_parser_ignores_non_json_summary_notes(tmp_path: Path) -> None:
    # Given: mypy emits a configuration note alongside JSON diagnostics.
    output = (
        "pyproject.toml: note: unused-section-warnings are disabled\n"
        + json.dumps(
            {
                "file": str(tmp_path / "sample.py"),
                "line": 8,
                "column": 2,
                "message": "incompatible value",
                "code": "assignment",
                "severity": "error",
            }
        )
    )

    # When: the quality parser consumes the tool output.
    diagnostics = parse_mypy_output(output, tmp_path)

    # Then: notes do not crash the gate and diagnostics remain comparable.
    assert sum(diagnostics.values()) == 1


def test_format_parser_hashes_file_content_without_retaining_it(
    tmp_path: Path,
) -> None:
    # Given
    secret_marker = "TOP_SECRET_TEST_VALUE"
    source_path = tmp_path / "sample.py"
    source_path.write_text(f'value = "{secret_marker}"\n', encoding="utf-8")
    output = f"Would reformat: {source_path}\n1 file would be reformatted\n"

    # When
    diagnostics = parse_ruff_format_output(output, tmp_path)

    # Then
    assert sum(diagnostics.values()) == 1
    assert secret_marker not in "".join(diagnostics)
    assert next(iter(diagnostics)).startswith("sample.py:format:")


def test_historical_subset_passes_and_reports_resolved_diagnostics() -> None:
    # Given
    baseline = Counter({"a.py:F401:hash-a": 1, "b.py:F841:hash-b": 1})
    current = Counter({"a.py:F401:hash-a": 1})

    # When
    delta = compare_diagnostics(baseline, current)
    exit_code = quality_exit_code({"ruff": delta})
    summary = format_gate_summary({"ruff": delta})

    # Then
    assert exit_code == 0
    assert sum(delta.new.values()) == 0
    assert sum(delta.resolved.values()) == 1
    assert "resolved=1" in summary


def test_new_diagnostic_returns_failure_without_rendering_message_content() -> None:
    # Given
    secret_marker = "TOP_SECRET_TEST_VALUE"
    delta = DiagnosticDelta(
        new=Counter({"new.py:F401:message-hash": 1}),
        resolved=Counter(),
    )

    # When
    exit_code = quality_exit_code({"ruff": delta})
    summary = format_gate_summary({"ruff": delta})

    # Then
    assert exit_code == 1
    assert "new=1" in summary
    assert secret_marker not in summary
