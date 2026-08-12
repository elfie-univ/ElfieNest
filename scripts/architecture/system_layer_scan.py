"""Ratchet machine-checkable parts of the system architecture contract."""

from __future__ import annotations

import argparse
import ast
import runpy
import sys
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, List, Mapping, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOTS = ("elfie", "nest")
TECHNICAL_MODULES = frozenset(
    {
        "httpx",
        "requests",
        "socket",
        "sqlite3",
        "subprocess",
        "urllib",
        "websockets",
    }
)
FORBIDDEN_ROOT_IMPORTS: Mapping[str, FrozenSet[str]] = {
    "elfie": frozenset(
        {
            "ai_runtime",
            "app",
            "godot_project",
            "godot_runtime",
            "infrastructure",
            "nest",
        }
    ),
    "nest": frozenset(
        {
            "ai_runtime",
            "app",
            "elfie",
            "godot_project",
            "godot_runtime",
            "infrastructure",
        }
    ),
}
RULE_NAMES = frozenset(
    {
        "elfie_forbidden_module_imports",
        "elfie_technical_imports",
        "nest_forbidden_module_imports",
        "nest_technical_imports",
    }
)


def _python_files(root: Path) -> Iterator[Path]:
    if root.is_dir():
        yield from sorted(path for path in root.rglob("*.py") if path.is_file())


def _imported_modules(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def collect_system_layer_violations(
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, FrozenSet[str]]:
    project_root = project_root.resolve()
    mutable: Dict[str, Set[str]] = {rule: set() for rule in RULE_NAMES}
    for core in CORE_ROOTS:
        root = project_root / core
        for path in _python_files(root):
            relative = path.relative_to(project_root).as_posix()
            for module in _imported_modules(path):
                top_level = module.split(".", 1)[0]
                location = f"{relative} -> {module}"
                if top_level in FORBIDDEN_ROOT_IMPORTS[core]:
                    mutable[f"{core}_forbidden_module_imports"].add(location)
                if top_level in TECHNICAL_MODULES:
                    mutable[f"{core}_technical_imports"].add(location)
    return {rule: frozenset(values) for rule, values in sorted(mutable.items())}


def load_python_baseline(path: Path) -> Dict[str, FrozenSet[str]]:
    namespace = runpy.run_path(str(path))
    raw = namespace.get("LEGACY_SYSTEM_LAYER_VIOLATIONS")
    if not isinstance(raw, dict):
        raise ValueError(f"{path} does not define LEGACY_SYSTEM_LAYER_VIOLATIONS")
    return {str(rule): frozenset(entries) for rule, entries in raw.items()}


def compare_with_baseline(
    current: Dict[str, FrozenSet[str]],
    baseline: Dict[str, FrozenSet[str]],
    *,
    mode: str,
) -> List[str]:
    failures: List[str] = []
    if set(current) != set(baseline):
        failures.append(
            "rule set differs: "
            f"current_only={sorted(set(current) - set(baseline))}, "
            f"baseline_only={sorted(set(baseline) - set(current))}"
        )
        return failures
    for rule in sorted(current):
        added = sorted(current[rule] - baseline[rule])
        removed = sorted(baseline[rule] - current[rule])
        if added:
            failures.append(f"{rule}: new violations: {added}")
        if mode == "exact" and removed:
            failures.append(f"{rule}: stale baseline entries: {removed}")
    return failures


def deny_all_failures(current: Dict[str, FrozenSet[str]]) -> List[str]:
    """Reject every detected violation after the legacy baseline is deleted."""

    return [
        f"{rule}: violations are forbidden in deny-all mode: {sorted(entries)}"
        for rule, entries in sorted(current.items())
        if entries
    ]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--mode", choices=("exact", "subset", "deny-all"), default="exact"
    )
    args = parser.parse_args(argv)

    current = collect_system_layer_violations(args.project_root)
    if args.mode == "deny-all":
        failures = deny_all_failures(current)
    else:
        if args.baseline is None:
            parser.error(f"--baseline is required in {args.mode} mode")
        baseline = load_python_baseline(args.baseline)
        failures = compare_with_baseline(current, baseline, mode=args.mode)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    total = sum(len(entries) for entries in current.values())
    print(f"System architecture {args.mode} check passed: {total} known entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
