"""Classify every structural entry in contract-guarded cleanup scopes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ScopeEntry:
    """One permitted direct child and its architectural disposition."""

    kind: str
    disposition: str
    conformance_id: Optional[str] = None


@dataclass(frozen=True)
class DirectoryScope:
    """A directory whose direct children must all be classified."""

    relative_path: str
    entries: Dict[str, ScopeEntry]


def _files(*names: str, disposition: str = "support") -> Dict[str, ScopeEntry]:
    return {name: ScopeEntry("file", disposition) for name in names}


NEST_ROOT_ENTRIES: Dict[str, ScopeEntry] = {
    **_files("AGENTS.md", "README.md", "README_zh.md"),
    **_files(
        "__init__.py",
        "config.py",
        "events.py",
        "nest.py",
        "public.py",
        "snapshot.py",
        disposition="target",
    ),
    "__pycache__": ScopeEntry("directory", "generated"),
    "time_environment": ScopeEntry("directory", "target"),
    "space_facilities": ScopeEntry("directory", "target"),
    "living_rules": ScopeEntry("directory", "target"),
    "elfie_interaction": ScopeEntry("directory", "target"),
}

GODOT_ROOT_ENTRIES: Dict[str, ScopeEntry] = {
    **_files("AGENTS.md", "README.md", "README_zh.md", "WEB_EXPORT.md"),
    **_files(
        "export_presets.cfg",
        "lab_preview_controller.gd",
        "lab_preview_controller.gd.uid",
        "main.gd",
        "main.gd.uid",
        "main.tscn",
        "project.godot",
        disposition="target",
    ),
    ".godot": ScopeEntry("directory", "generated"),
    "characters": ScopeEntry("directory", "authored-content"),
    "rooms": ScopeEntry("directory", "authored-content"),
    "runtime": ScopeEntry("directory", "target"),
    "scripts": ScopeEntry("directory", "developer-input"),
    "ui": ScopeEntry("directory", "presentation"),
}

GODOT_RUNTIME_ENTRIES: Dict[str, ScopeEntry] = {
    **_files("species_catalog.gd", disposition="target"),
    **_files("species_catalog.gd.uid", disposition="generated"),
    "actor": ScopeEntry("directory", "target"),
    "endpoint": ScopeEntry("directory", "target"),
    "lab": ScopeEntry("directory", "presentation"),
    "observer": ScopeEntry("directory", "presentation"),
    "world": ScopeEntry("directory", "target"),
}

GODOT_SCRIPT_ENTRIES: Dict[str, ScopeEntry] = {
    "test": ScopeEntry("directory", "developer-input"),
    "tools": ScopeEntry("directory", "developer-input"),
}

STRUCTURAL_SCOPES: Tuple[DirectoryScope, ...] = (
    DirectoryScope("nest", NEST_ROOT_ENTRIES),
    DirectoryScope("godot_project", GODOT_ROOT_ENTRIES),
    DirectoryScope("godot_project/runtime", GODOT_RUNTIME_ENTRIES),
    DirectoryScope("godot_project/scripts", GODOT_SCRIPT_ENTRIES),
)

# These are temporary migration locations, not permanent allowed architecture.
# The base-aware governance checker prevents them from gaining new files; the
# entries remain empty after the corresponding structural row is closed.
TEMPORARY_CLEANUP_PREFIXES: Tuple[Tuple[str, str], ...] = ()


def temporary_cleanup_owner(relative_path: str) -> Optional[str]:
    """Return the conformance row owning a temporary path, if any."""

    normalized = relative_path.rstrip("/")
    for prefix, conformance_id in TEMPORARY_CLEANUP_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return conformance_id
    return None


def collect_structural_scope_violations(project_root: Path) -> List[str]:
    """Report missing roots, unknown direct entries and kind mismatches."""

    failures: List[str] = []
    for scope in STRUCTURAL_SCOPES:
        root = project_root / scope.relative_path
        if not root.is_dir():
            failures.append(f"{scope.relative_path}: required structural scope missing")
            continue
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            rule = scope.entries.get(path.name)
            relative = path.relative_to(project_root).as_posix()
            if rule is None:
                failures.append(f"{relative}: unclassified structural path")
                continue
            actual_kind = "directory" if path.is_dir() else "file"
            if actual_kind != rule.kind:
                failures.append(
                    f"{relative}: expected {rule.kind}, found {actual_kind}"
                )
    return failures


def classified_entries(project_root: Path) -> Iterable[Tuple[str, ScopeEntry]]:
    """Yield present, classified entries for diagnostic reporting."""

    for scope in STRUCTURAL_SCOPES:
        root = project_root / scope.relative_path
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            rule = scope.entries.get(path.name)
            if rule is not None:
                yield path.relative_to(project_root).as_posix(), rule


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--show-inventory", action="store_true")
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    failures = collect_structural_scope_violations(project_root)
    if failures:
        for failure in failures:
            print(failure)
        return 1
    counts: Dict[str, int] = {}
    entries = list(classified_entries(project_root))
    for relative_path, rule in entries:
        counts[rule.disposition] = counts.get(rule.disposition, 0) + 1
        if args.show_inventory:
            owner = f" ({rule.conformance_id})" if rule.conformance_id else ""
            print(f"{relative_path}: {rule.disposition}{owner}")
    summary = ", ".join(f"{key}={counts[key]}" for key in sorted(counts))
    print(f"Structural cleanup scope classified: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
