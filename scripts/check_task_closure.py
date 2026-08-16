#!/usr/bin/env python3
"""Validate the evidence matrix required before a task can be delivered."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STATUSES = {
    "not_started",
    "implementing",
    "verifying",
    "complete",
    "blocked",
}
REQUIRED_ROW_FIELDS = {
    "id",
    "requirement",
    "status",
    "implementation",
    "automated_tests",
    "runtime_scenarios",
    "platform_conditions",
    "evidence",
    "residuals",
    "blockers",
}
EVIDENCE_PREFIXES = ("command:", "artifact:", "host:", "review:")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _matches_scope(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _conformance_statuses(project_root: Path) -> dict[str, list[tuple[str, str]]]:
    statuses: dict[str, list[tuple[str, str]]] = {}
    root = project_root / "docs" / "developer" / "conformance"
    for path in sorted(root.glob("*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 3 or cells[2] not in {"open", "in progress", "closed"}:
                continue
            statuses.setdefault(cells[0], []).append((cells[2], str(path)))
    return statuses


def changed_paths(project_root: Path, base_sha: Optional[str]) -> list[str]:
    """Return tracked and untracked paths in the candidate worktree."""

    if base_sha:
        diff = subprocess.run(
            ["git", "diff", "--name-only", base_sha, "--"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    else:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return sorted({path for path in [*diff, *untracked] if path})


def validate_task_closure(
    document: Mapping[str, Any],
    *,
    changed: Iterable[str] = (),
    closure_file: str = "",
    mode: str = "complete",
    conformance: Optional[Mapping[str, list[tuple[str, str]]]] = None,
) -> list[str]:
    """Return actionable validation failures for a task closure document."""

    failures: list[str] = []
    if document.get("schema_version") != 1:
        failures.append("schema_version must be 1")
    if not isinstance(document.get("task"), str) or not document["task"].strip():
        failures.append("task must be a non-empty string")

    scope_value = document.get("scope")
    scope: Sequence[str]
    if not _is_string_list(scope_value):
        failures.append("scope must be a non-empty list of bounded path/glob strings")
        scope = []
    else:
        scope = cast(Sequence[str], scope_value)
        for pattern in scope:
            if pattern in {"*", "**", "**/*"}:
                failures.append(f"scope is too broad: {pattern}")

    contract_refs = document.get("contract_refs")
    if not isinstance(contract_refs, list) or not all(
        isinstance(item, str) and item.strip() for item in contract_refs
    ):
        failures.append("contract_refs must be a list of strings (possibly empty)")

    conformance_block = document.get("conformance")
    if not isinstance(conformance_block, dict):
        failures.append("conformance must contain rows and an explicit reason")
        conformance_block = {}
    conformance_rows = conformance_block.get("rows")
    reason = conformance_block.get("reason")
    if not _is_string_list(conformance_rows):
        failures.append("conformance.rows must be a list of strings")
        conformance_rows = []
    if not conformance_rows and (not isinstance(reason, str) or not reason.strip()):
        failures.append("conformance.reason is required when conformance.rows is empty")
    if conformance_rows and reason not in ("", None):
        failures.append("conformance.reason must be empty when rows are listed")

    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        failures.append("rows must be a non-empty list")
        rows = []

    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        prefix = f"rows[{index}]"
        if not isinstance(row, dict):
            failures.append(f"{prefix} must be an object")
            continue
        missing = REQUIRED_ROW_FIELDS - set(row)
        if missing:
            failures.append(f"{prefix} missing fields: {sorted(missing)}")
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id.strip():
            failures.append(f"{prefix}.id must be a non-empty string")
        elif row_id in seen_ids:
            failures.append(f"duplicate row id: {row_id}")
        else:
            seen_ids.add(row_id)
        status = row.get("status")
        if status not in ALLOWED_STATUSES:
            failures.append(f"{prefix}.status is invalid: {status!r}")

        for field in (
            "implementation",
            "automated_tests",
            "runtime_scenarios",
            "platform_conditions",
            "evidence",
            "residuals",
            "blockers",
        ):
            if field in row and not isinstance(row[field], list):
                failures.append(f"{prefix}.{field} must be a list")

        if status == "blocked" and not _is_string_list(row.get("blockers")):
            failures.append(f"{prefix}.blockers must explain the blocking condition")
        if status == "complete":
            for field in (
                "implementation",
                "automated_tests",
                "runtime_scenarios",
                "platform_conditions",
                "evidence",
            ):
                if not _is_string_list(row.get(field)):
                    failures.append(f"{prefix}.{field} is required for complete")
            if row.get("residuals") != []:
                failures.append(f"{prefix}.residuals must be [] for complete")
            if row.get("blockers") != []:
                failures.append(f"{prefix}.blockers must be [] for complete")
            evidence = row.get("evidence", [])
            if isinstance(evidence, list):
                if not any(item.startswith("command:") for item in evidence):
                    failures.append(f"{prefix}.evidence needs a command: entry")
                if not any(
                    item.startswith(prefix_value)
                    for item in evidence
                    for prefix_value in ("artifact:", "host:", "review:")
                ):
                    failures.append(
                        f"{prefix}.evidence needs an artifact:, host:, or review: entry"
                    )

    changed_list = sorted(set(changed))
    if closure_file:
        changed_list = [path for path in changed_list if path != closure_file]
    unclassified = [path for path in changed_list if not _matches_scope(path, scope)]
    for path in unclassified:
        failures.append(f"changed path is outside task scope: {path}")

    if mode == "complete":
        incomplete = [
            str(row.get("id", index))
            for index, row in enumerate(rows)
            if not isinstance(row, dict) or row.get("status") != "complete"
        ]
        if incomplete:
            failures.append(f"task has non-complete rows: {', '.join(incomplete)}")

    if conformance_rows and conformance is not None and mode == "complete":
        for row_id in conformance_rows:
            matches = conformance.get(row_id, [])
            if len(matches) != 1:
                failures.append(
                    f"conformance row {row_id} must resolve to exactly one English row"
                )
            elif matches[0][0] != "closed":
                failures.append(
                    f"conformance row {row_id} is {matches[0][0]}, not closed"
                )

    return failures


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="task closure JSON path")
    parser.add_argument("--base-sha", help="immutable base commit for scope checks")
    parser.add_argument(
        "--mode",
        choices=("progress", "complete"),
        default="complete",
        help="progress validates shape; complete also requires every row closed",
    )
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ task closure: cannot read {path}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(document, dict):
        print("❌ task closure: root JSON value must be an object", file=sys.stderr)
        return 1

    try:
        relative_file = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        print("❌ task closure: --file must be inside the repository", file=sys.stderr)
        return 1
    failures = validate_task_closure(
        document,
        changed=changed_paths(PROJECT_ROOT, args.base_sha),
        closure_file=relative_file,
        mode=args.mode,
        conformance=_conformance_statuses(PROJECT_ROOT),
    )
    if failures:
        print("❌ task closure gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"✅ task closure gate passed ({args.mode}): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
