"""Reject pull requests that mix architecture governance and production code."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

PRODUCTION_ROOTS = (
    "app/",
    "elfie/",
    "godot_project/",
    "godot_runtime/",
    "infrastructure/",
    "nest/",
)
PRODUCTION_DOCUMENT_SUFFIXES = frozenset({".md", ".rst"})
GOVERNANCE_PREFIXES = (
    "docs/developer/contracts/",
    "docs/developer/decisions/",
    "docs/zh/developer/contracts/",
    "docs/zh/developer/decisions/",
    "scripts/architecture/",
)
GOVERNANCE_EXACT = {
    ".pre-commit-config.yaml",
    ".github/workflows/ci.yml",
    "scripts/check_quality_baseline.py",
    "test/architecture/AGENTS.md",
    "test/architecture/test_app_layer_boundaries.py",
    "test/architecture/test_system_layer_boundaries.py",
}
CONTRACT_VERSION_PATTERN = re.compile(
    r"\*\*(?:Contract version|契约版本)[：:]\*\*\s*([^\s]+)"
)
ARCHITECTURE_TEST_PREFIX = "test/architecture/"
ARCHITECTURE_BASELINE_PREFIX = "test/architecture/baselines/"
ARCHITECTURE_BASELINE_SUPPORT_FILES = frozenset(
    {"test/architecture/baselines/__init__.py"}
)
GOVERNANCE_CONTRACT_PATH = "docs/developer/contracts/repository-governance.md"
BASELINE_VARIABLES = {
    "test/architecture/baselines/app_layer.py": "LEGACY_APP_LAYER_VIOLATIONS",
    "test/architecture/baselines/system_layer.py": "LEGACY_SYSTEM_LAYER_VIOLATIONS",
}
FROZEN_MACRO_CONTRACTS = frozenset(
    {
        "docs/developer/contracts/system.md",
        "docs/zh/developer/contracts/system.md",
    }
)


def is_governance_file(path: str) -> bool:
    if path in BASELINE_VARIABLES:
        return False
    return (
        path.endswith("/AGENTS.md")
        or path == "AGENTS.md"
        or path in GOVERNANCE_EXACT
        or path.startswith(GOVERNANCE_PREFIXES)
        or path.startswith(ARCHITECTURE_TEST_PREFIX)
    )


def is_production_source(path: str) -> bool:
    if not path.startswith(PRODUCTION_ROOTS):
        return False
    if path.endswith("/AGENTS.md") or path.endswith("/README.md"):
        return False
    return Path(path).suffix.lower() not in PRODUCTION_DOCUMENT_SUFFIXES


def classify_paths(paths: Iterable[str]) -> Tuple[Set[str], Set[str]]:
    governance = {path for path in paths if is_governance_file(path)}
    production = {path for path in paths if is_production_source(path)}
    return governance, production


def changed_paths(base_sha: str) -> List[str]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMRTUXB",
            f"{base_sha}...HEAD",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _contract_mirror(path: str) -> Optional[str]:
    english_prefix = "docs/developer/contracts/"
    chinese_prefix = "docs/zh/developer/contracts/"
    if path.startswith(english_prefix):
        return chinese_prefix + path[len(english_prefix) :]
    if path.startswith(chinese_prefix):
        return english_prefix + path[len(chinese_prefix) :]
    return None


def _decision_mirror(path: str) -> Optional[str]:
    english_prefix = "docs/developer/decisions/"
    chinese_prefix = "docs/zh/developer/decisions/"
    if path.startswith(english_prefix):
        return chinese_prefix + path[len(english_prefix) :]
    if path.startswith(chinese_prefix):
        return english_prefix + path[len(chinese_prefix) :]
    return None


def _version(source: str, path: str) -> str:
    match = CONTRACT_VERSION_PATTERN.search(source)
    if match is None:
        raise ValueError(f"contract version missing: {path}")
    return match.group(1)


def _base_source(base_sha: str, path: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "show", f"{base_sha}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def _decision_changes(paths: Iterable[str]) -> Set[str]:
    return {
        path
        for path in paths
        if path.startswith("docs/developer/decisions/")
        or path.startswith("docs/zh/developer/decisions/")
    }


def _baseline_entries(source: str, path: str) -> Dict[str, FrozenSet[str]]:
    variable = BASELINE_VARIABLES[path]
    tree = ast.parse(source, filename=path)
    value: Optional[ast.AST] = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == variable:
                value = node.value
                break
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == variable
                for target in node.targets
            ):
                value = node.value
                break
    if not isinstance(value, ast.Dict):
        raise ValueError(f"{path} does not define a literal {variable} dictionary")

    result: Dict[str, FrozenSet[str]] = {}
    for key_node, entries_node in zip(value.keys, value.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(
            key_node.value, str
        ):
            raise ValueError(f"{path} has a non-string baseline rule")
        if (
            isinstance(entries_node, ast.Call)
            and isinstance(entries_node.func, ast.Name)
            and entries_node.func.id == "frozenset"
        ):
            if not entries_node.args:
                entry_nodes: Iterable[ast.AST] = ()
            elif len(entries_node.args) == 1 and isinstance(
                entries_node.args[0], (ast.Set, ast.List, ast.Tuple)
            ):
                entry_nodes = entries_node.args[0].elts
            else:
                raise ValueError(f"{path} has an unsupported frozenset value")
        else:
            raise ValueError(f"{path} baseline values must be frozenset literals")
        entries: Set[str] = set()
        for entry_node in entry_nodes:
            if not isinstance(entry_node, ast.Constant) or not isinstance(
                entry_node.value, str
            ):
                raise ValueError(f"{path} has a non-string baseline entry")
            entries.add(entry_node.value)
        result[key_node.value] = frozenset(entries)
    return result


def validate_baseline_changes(
    base_sha: str,
    paths: Iterable[str],
    *,
    governance: Set[str],
) -> List[str]:
    """Allow exact legacy baselines to shrink, never to be rewritten."""

    changed = set(paths)
    baseline_paths = {
        path
        for path in changed
        if path.startswith(ARCHITECTURE_BASELINE_PREFIX)
        and path not in ARCHITECTURE_BASELINE_SUPPORT_FILES
    }
    if not baseline_paths:
        return []

    base_has_governance = _base_source(base_sha, GOVERNANCE_CONTRACT_PATH) is not None
    failures: List[str] = []
    unknown = baseline_paths - set(BASELINE_VARIABLES)
    if unknown:
        failures.append(f"unregistered architecture baseline: {sorted(unknown)}")
    if governance and base_has_governance:
        failures.append("governance changes may not edit legacy architecture baselines")

    for path in sorted(baseline_paths & set(BASELINE_VARIABLES)):
        base_source = _base_source(base_sha, path)
        candidate_path = Path(path)
        if base_source is None:
            if base_has_governance and candidate_path.is_file():
                failures.append(f"new architecture baseline is forbidden: {path}")
            continue
        if not candidate_path.is_file():
            continue
        try:
            base_entries = _baseline_entries(base_source, path)
            candidate_entries = _baseline_entries(
                candidate_path.read_text(encoding="utf-8"), path
            )
        except (SyntaxError, ValueError) as error:
            failures.append(str(error))
            continue
        if set(candidate_entries) != set(base_entries):
            failures.append(f"architecture baseline rule set changed: {path}")
            continue
        for rule, entries in candidate_entries.items():
            added = entries - base_entries[rule]
            if added:
                failures.append(
                    f"architecture baseline entries added or rewritten: "
                    f"{path}:{rule}: {sorted(added)}"
                )
    return failures


def validate_governance_rule_changes(paths: Iterable[str]) -> List[str]:
    """Require an ADR update whenever executable architecture rules change."""

    changed = set(paths)
    rule_changes = {
        path
        for path in changed
        if (
            path == ".github/workflows/ci.yml"
            or path == "AGENTS.md"
            or path.endswith("/AGENTS.md")
            or path.startswith("scripts/architecture/")
            or (
                path.startswith(ARCHITECTURE_TEST_PREFIX)
                and not path.startswith(ARCHITECTURE_BASELINE_PREFIX)
            )
        )
    }
    if rule_changes and not _decision_changes(changed):
        return [
            "architecture rule changed without a bilingual ADR update: "
            f"{sorted(rule_changes)}"
        ]
    return []


def validate_contract_changes(base_sha: str, paths: Iterable[str]) -> List[str]:
    """Require bilingual version bumps and an ADR for contract changes."""

    changed = set(paths)
    contract_paths = sorted(path for path in changed if _contract_mirror(path))
    if not contract_paths:
        return []

    failures: List[str] = []
    checked_pairs: Set[frozenset[str]] = set()
    for path in contract_paths:
        mirror = _contract_mirror(path)
        assert mirror is not None
        pair = frozenset({path, mirror})
        if pair in checked_pairs:
            continue
        checked_pairs.add(pair)
        if mirror not in changed:
            failures.append(f"contract mirror not changed with {path}: {mirror}")
            continue
        for current_path in sorted(pair):
            current_source = Path(current_path).read_text(encoding="utf-8")
            base_source = _base_source(base_sha, current_path)
            if base_source is not None and _version(
                current_source, current_path
            ) == _version(base_source, current_path):
                failures.append(f"contract version not bumped: {current_path}")

    decision_changes = _decision_changes(changed)
    if not decision_changes:
        failures.append("contract changed without a matching ADR change")
    macro_contract_changed = bool(changed & FROZEN_MACRO_CONTRACTS)
    base_has_macro_contract = macro_contract_changed and any(
        _base_source(base_sha, path) is not None for path in FROZEN_MACRO_CONTRACTS
    )
    if macro_contract_changed and base_has_macro_contract:
        new_decisions = {
            path
            for path in decision_changes
            if not path.endswith("/index.md") and _base_source(base_sha, path) is None
        }
        has_bilingual_new_decision = any(
            (mirror := _decision_mirror(path)) is not None and mirror in new_decisions
            for path in new_decisions
        )
        if not has_bilingual_new_decision:
            failures.append(
                "frozen macro architecture changed without a new standalone "
                "bilingual ADR"
            )
    return failures


def validate_decision_mirrors(paths: Iterable[str]) -> List[str]:
    """Require every changed ADR to change with its language mirror."""

    changed = set(paths)
    failures: List[str] = []
    for path in sorted(changed):
        mirror = _decision_mirror(path)
        if mirror is not None and mirror not in changed:
            failures.append(f"ADR mirror not changed with {path}: {mirror}")
    return failures


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-sha", required=True)
    args = parser.parse_args(argv)
    paths = changed_paths(args.base_sha)
    governance, production = classify_paths(paths)
    if governance and production:
        print(
            "Architecture governance and production source must be reviewed "
            "in separate pull requests.",
            file=sys.stderr,
        )
        print(f"governance: {sorted(governance)}", file=sys.stderr)
        print(f"production: {sorted(production)}", file=sys.stderr)
        return 1
    governance_failures = [
        *validate_baseline_changes(args.base_sha, paths, governance=governance),
        *validate_contract_changes(args.base_sha, paths),
        *validate_decision_mirrors(paths),
        *validate_governance_rule_changes(paths),
    ]
    if governance_failures:
        for failure in governance_failures:
            print(failure, file=sys.stderr)
        return 1
    kind = "governance" if governance else "product/migration"
    print(f"Architecture change class: {kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
