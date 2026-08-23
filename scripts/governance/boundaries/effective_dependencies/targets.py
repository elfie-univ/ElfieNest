"""Normalize effective repository targets found in dynamic execution arguments."""

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


def normalize_module_target(value: str, *, package: str = "") -> str:
    """Return one repository module target or an empty external target.

    ``importlib.import_module`` accepts package-relative module names such as
    ``.api``. Resolve those against the caller package before applying the
    repository-root check; command and script paths continue to use the
    package-free form.
    """
    cleaned = value.strip().replace("\\", "/")
    if cleaned.startswith(".") and not cleaned.startswith("./"):
        if not package:
            return ""
        level = len(cleaned) - len(cleaned.lstrip("."))
        package_parts = package.split(".")
        keep = len(package_parts) - (level - 1)
        if keep < 0:
            return ""
        suffix = cleaned[level:].strip("/")
        resolved_parts = package_parts[:keep]
        if suffix:
            resolved_parts.extend(suffix.split("/"))
        cleaned = ".".join(resolved_parts)
    else:
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
