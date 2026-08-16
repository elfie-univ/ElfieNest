"""Tests for the evidence-backed task completion gate."""

from __future__ import annotations

from scripts.check_task_closure import validate_task_closure


def _document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "task": "closure gate",
        "contract_refs": [],
        "scope": ["scripts/check_task_closure.py", "test/scripts/**"],
        "conformance": {"rows": [], "reason": "governance-only gate change"},
        "rows": [
            {
                "id": "REQ-001",
                "requirement": "A complete row needs replayable evidence",
                "status": "complete",
                "implementation": ["scripts/check_task_closure.py"],
                "automated_tests": ["test/scripts/test_check_task_closure.py"],
                "runtime_scenarios": ["Run the checker against a valid matrix"],
                "platform_conditions": ["CPython 3.9.25"],
                "evidence": [
                    "command: pytest test/scripts/test_check_task_closure.py",
                    "artifact: checker output",
                ],
                "residuals": [],
                "blockers": [],
            }
        ],
    }
    document.update(overrides)
    return document


def test_complete_matrix_passes_with_bounded_scope() -> None:
    assert (
        validate_task_closure(
            _document(),
            changed=[
                "scripts/check_task_closure.py",
                "test/scripts/test_check_task_closure.py",
            ],
            closure_file="task-closure.json",
        )
        == []
    )


def test_open_row_and_residual_block_complete_mode() -> None:
    document = _document()
    rows = document["rows"]
    assert isinstance(rows, list)
    row = dict(rows[0])
    row["status"] = "verifying"
    row["residuals"] = ["live crash scenario not run"]
    document["rows"] = [row]
    failures = validate_task_closure(document)
    assert any("non-complete rows" in failure for failure in failures)


def test_unclassified_path_and_catch_all_scope_are_rejected() -> None:
    document = _document(scope=["**"])
    failures = validate_task_closure(
        document,
        changed=["unrelated.py"],
        closure_file="task-closure.json",
    )
    assert any("scope is too broad" in failure for failure in failures)


def test_listed_conformance_row_must_be_closed() -> None:
    document = _document(
        conformance={"rows": ["LFC-005"], "reason": ""},
    )
    failures = validate_task_closure(
        document,
        conformance={
            "LFC-005": [
                ("in progress", "docs/developer/conformance/service-lifecycle.md")
            ]
        },
    )
    assert failures == ["conformance row LFC-005 is in progress, not closed"]


def test_progress_mode_allows_an_open_listed_conformance_row() -> None:
    document = _document(
        conformance={"rows": ["LFC-005"], "reason": ""},
    )
    failures = validate_task_closure(
        document,
        mode="progress",
        conformance={
            "LFC-005": [
                ("in progress", "docs/developer/conformance/service-lifecycle.md")
            ]
        },
    )
    assert failures == []
