"""Reject repository dependencies hidden behind dynamic execution APIs."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, FrozenSet, Iterator, List, Mapping, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
project_root_text = str(PROJECT_ROOT)
if project_root_text not in sys.path:
    sys.path.insert(0, project_root_text)

from scripts.architecture.effective_dependency_python import (  # noqa: E402
    python_dependencies,
)
from scripts.architecture.effective_dependency_targets import (
    REPOSITORY_ROOTS,
    SOURCE_SUFFIXES,
)  # noqa: E402
from scripts.architecture.effective_dependency_text import (
    godot_dependencies,
    node_dependencies,
    shell_dependencies,
)  # noqa: E402

IGNORED_DIRECTORIES = frozenset(
    {".git", ".mypy_cache", ".pytest_cache", ".venv", "build", "dist", "node_modules"}
)
ROOT_SCRIPT_OWNERS: Mapping[str, str] = {
    "developer.sh": "devtools",
    "elfienest.sh": "scripts",
    "install.sh": "scripts",
}
ALLOWED_TARGET_ROOTS: Mapping[str, FrozenSet[str]] = {
    "interface": frozenset({"app"}),
    "feature": frozenset({"app", "elfie", "nest"}),
    "orchestration": frozenset({"app", "elfie", "nest"}),
    "bootstrap": frozenset({"app", "elfie", "infrastructure", "nest", "scripts"}),
    "infrastructure": frozenset({"app", "elfie", "infrastructure", "nest"}),
    "elfie": frozenset({"elfie"}),
    "nest": frozenset({"nest"}),
    "scripts": frozenset({"app", "elfie", "infrastructure", "nest", "scripts"}),
    "devtools": REPOSITORY_ROOTS,
    "docs": frozenset({"docs"}),
    "godot": frozenset({"godot_project"}),
    "test": REPOSITORY_ROOTS,
    "unowned": frozenset(),
}
RULE_LEDGER_IDS: Mapping[str, str] = {
    "interface_effective_dependencies": "APP-001",
    "feature_effective_dependencies": "APP-002",
    "orchestration_effective_dependencies": "APP-002",
    "infrastructure_effective_dependencies": "APP-002",
    "elfie_effective_dependencies": "SYS-002",
    "nest_effective_dependencies": "SYS-003",
    "production_tooling_effective_dependencies": "SYS-001",
}


def _source_files(project_root: Path) -> Iterator[Path]:
    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        yield path


def _source_boundary(relative: str) -> str:
    if relative in ROOT_SCRIPT_OWNERS:
        return ROOT_SCRIPT_OWNERS[relative]
    app_boundaries = {
        "app/interfaces/": "interface",
        "app/features/": "feature",
        "app/orchestration/": "orchestration",
        "app/bootstrap/": "bootstrap",
    }
    for prefix, boundary in app_boundaries.items():
        if relative.startswith(prefix):
            return boundary
    fixed_boundaries = {
        "test/": "test",
        "docs/": "docs",
        "godot_project/": "godot",
    }
    for prefix, boundary in fixed_boundaries.items():
        if relative.startswith(prefix):
            return boundary
    for prefix in ("devtools", "elfie", "infrastructure", "nest", "scripts"):
        if relative == prefix or relative.startswith(f"{prefix}/"):
            return prefix
    return "unowned"


def _is_allowed(source: str, boundary: str, target: str) -> bool:
    target_parts = target.split(".")
    target_root = target_parts[0]
    if target_root not in ALLOWED_TARGET_ROOTS[boundary]:
        return False
    if target_root != "app":
        return True
    if boundary == "interface":
        if target.startswith("app.interfaces"):
            return True
        if target.startswith("app.features."):
            return len(target_parts) == 3
        if target.startswith("app.orchestration."):
            return len(target_parts) == 3
        return False
    if boundary == "feature" and target.startswith("app.features."):
        source_parts = source.split("/")
        source_domain = source_parts[2] if len(source_parts) > 2 else ""
        target_domain = target_parts[2] if len(target_parts) > 2 else ""
        return target_domain == source_domain or len(target_parts) == 3
    if boundary == "orchestration" and target.startswith("app.features."):
        return len(target_parts) == 3
    if boundary == "infrastructure" and target.startswith("app.features."):
        return len(target_parts) == 3 or target_parts[-1] in {"models", "ports"}
    if boundary == "infrastructure" and target.startswith("app.orchestration."):
        return len(target_parts) == 3 or target_parts[-1] in {"models", "ports"}
    if boundary in {"feature", "orchestration"}:
        return target.startswith(f"app.{boundary}") or target.startswith("app.features")
    return True


def _rule_for(boundary: str, target: str) -> str:
    if target == "devtools" or target.startswith("devtools."):
        return "production_tooling_effective_dependencies"
    return {
        "interface": "interface_effective_dependencies",
        "feature": "feature_effective_dependencies",
        "orchestration": "orchestration_effective_dependencies",
        "infrastructure": "infrastructure_effective_dependencies",
        "elfie": "elfie_effective_dependencies",
        "nest": "nest_effective_dependencies",
        "bootstrap": "production_tooling_effective_dependencies",
        "scripts": "production_tooling_effective_dependencies",
        "docs": "production_tooling_effective_dependencies",
        "godot": "production_tooling_effective_dependencies",
        "unowned": "production_tooling_effective_dependencies",
    }[boundary]


def collect_effective_dependency_violations(
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, FrozenSet[str]]:
    """Collect forbidden resolvable edges across all repository source roots."""
    project_root = project_root.resolve()
    mutable: DefaultDict[str, Set[str]] = defaultdict(set)
    for rule in RULE_LEDGER_IDS:
        mutable[rule]
    parsers = {
        ".py": python_dependencies,
        ".sh": shell_dependencies,
        ".gd": godot_dependencies,
    }
    for path in _source_files(project_root):
        relative = path.relative_to(project_root).as_posix()
        boundary = _source_boundary(relative)
        dependencies = parsers.get(path.suffix, node_dependencies)(path)
        for line, mechanism, target in dependencies:
            if _is_allowed(relative, boundary, target):
                continue
            rule = _rule_for(boundary, target)
            mutable[rule].add(f"{relative}:{line} [{mechanism}] -> {target}")
    return {rule: frozenset(mutable[rule]) for rule in sorted(RULE_LEDGER_IDS)}


def deny_all_failures(current: Mapping[str, FrozenSet[str]]) -> List[str]:
    """Return stable failures for every forbidden effective dependency."""
    return [
        f"{rule}: effective dependencies are forbidden: {sorted(entries)}"
        for rule, entries in sorted(current.items())
        if entries
    ]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    failures = deny_all_failures(
        collect_effective_dependency_violations(args.project_root)
    )
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("Effective dependency check passed: 0 forbidden targets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
