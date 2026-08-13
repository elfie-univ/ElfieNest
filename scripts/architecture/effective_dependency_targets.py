"""Normalize repository targets found in dynamic execution arguments."""

from __future__ import annotations

from typing import Iterable, Set

REPOSITORY_ROOTS = frozenset(
    {
        "app",
        "devtools",
        "docs",
        "elfie",
        "godot_project",
        "infrastructure",
        "nest",
        "scripts",
    }
)
SOURCE_SUFFIXES = frozenset({".cjs", ".gd", ".js", ".mjs", ".py", ".sh", ".ts", ".tsx"})


def normalize_module_target(value: str) -> str:
    """Return one repository module target or an empty external target."""
    cleaned = value.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if cleaned.endswith(tuple(SOURCE_SUFFIXES)):
        cleaned = cleaned.rsplit(".", 1)[0]
    cleaned = cleaned.strip("/").replace("/", ".")
    if cleaned.endswith(".__main__") or cleaned.endswith(".__init__"):
        cleaned = cleaned.rsplit(".", 1)[0]
    root = cleaned.split(".", 1)[0]
    return cleaned if root in REPOSITORY_ROOTS else ""


def targets_from_tokens(tokens: Iterable[str]) -> Set[str]:
    """Extract module-mode and repository script targets from command tokens."""
    values = list(tokens)
    targets: Set[str] = set()
    for index, token in enumerate(values):
        if token == "-m" and index + 1 < len(values):
            target = normalize_module_target(values[index + 1])
            if target:
                targets.add(target)
        if token.endswith(tuple(SOURCE_SUFFIXES)):
            target = normalize_module_target(token)
            if target:
                targets.add(target)
    return targets
