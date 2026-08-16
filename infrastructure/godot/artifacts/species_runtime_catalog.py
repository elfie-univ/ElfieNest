"""Runtime species availability derived from one validated Godot package set."""

from __future__ import annotations

import json
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elfie.profile import SpeciesCatalog

from .species_package_validation import (
    GodotSpeciesValidationRunner,
    SpeciesPackageValidationError,
    validate_source_species_packages,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_ROOT = PROJECT_ROOT / "config"
DEFAULT_GODOT_PROJECT = PROJECT_ROOT / "godot_project"
DEFAULT_RUNTIME_MANIFEST = (
    PROJECT_ROOT / "build" / "components" / "godot-web" / "build-manifest.json"
)


@dataclass(frozen=True)
class ValidatedSpeciesRuntimeCatalog:
    """The only species set that Adoption may expose in a running process."""

    species_ids: tuple[str, ...]
    source: str

    def available_species_ids(self) -> tuple[str, ...]:
        return self.species_ids

    def is_available(self, species_id: str) -> bool:
        return species_id in self.species_ids


def build_species_runtime_catalog(
    catalog: SpeciesCatalog,
    *,
    config_root: Path = DEFAULT_CONFIG_ROOT,
    godot_project: Path = DEFAULT_GODOT_PROJECT,
    runtime_manifest: Path | None = None,
    godot_binary: Path | None = None,
    godot_runner: GodotSpeciesValidationRunner | None = None,
) -> ValidatedSpeciesRuntimeCatalog:
    """Use a matching export manifest, or validate the source package once.

    An old/missing export is never treated as usable. If the local Godot binary
    is unavailable, the returned set is empty instead of allowing a backend-only
    species to enter the adoption flow.
    """

    expected = tuple(
        definition.godot_package_id
        for definition in catalog.definitions
        if definition.resolvable
    )
    manifest_paths = _manifest_paths(runtime_manifest)
    for path in manifest_paths:
        manifest_ids = _matching_manifest_ids(path, catalog.digest, expected)
        if manifest_ids is not None:
            return ValidatedSpeciesRuntimeCatalog(manifest_ids, str(path))

    binary = godot_binary or _find_godot_binary()
    if binary is None:
        return ValidatedSpeciesRuntimeCatalog((), "godot-binary-missing")
    if godot_runner is None:
        raise RuntimeError(
            "build_species_runtime_catalog requires an injected Godot validation runner"
        )
    try:
        ids = validate_source_species_packages(
            config_root=config_root,
            godot_project=godot_project,
            godot_runner=godot_runner,
            godot_binary=binary,
        )
    except SpeciesPackageValidationError:
        return ValidatedSpeciesRuntimeCatalog((), "source-package-validation-failed")
    if set(ids) != set(expected):
        return ValidatedSpeciesRuntimeCatalog((), "source-package-set-mismatch")
    return ValidatedSpeciesRuntimeCatalog(tuple(sorted(ids)), "source-validation")


def _manifest_paths(explicit: Path | None) -> tuple[Path, ...]:
    if explicit is not None:
        return (explicit.expanduser().resolve(),)
    configured_dir = os.environ.get("ELFIENEST_GODOT_WEB_DIR", "").strip()
    paths = (
        Path(configured_dir).expanduser() / "build-manifest.json"
        if configured_dir
        else DEFAULT_RUNTIME_MANIFEST,
    )
    return tuple(path.resolve() for path in paths)


def _matching_manifest_ids(
    path: Path,
    catalog_digest: str,
    expected: tuple[str, ...],
) -> tuple[str, ...] | None:
    try:
        document: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    try:
        schema_version = int(document.get("schema_version", 0))
    except (TypeError, ValueError):
        return None
    if schema_version < 2:
        return None
    if document.get("species_catalog_digest") != catalog_digest:
        return None
    raw_ids = document.get("species_package_ids")
    if not isinstance(raw_ids, list) or any(
        not isinstance(item, str) for item in raw_ids
    ):
        return None
    ids = tuple(sorted(raw_ids))
    if ids != tuple(sorted(expected)):
        return None
    return ids


def _find_godot_binary() -> Path | None:
    configured = os.environ.get("GODOT_BIN", "").strip()
    candidates = [Path(configured).expanduser()] if configured else []
    for name in ("godot4", "godot", "Godot"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if platform.system() == "Darwin":
        candidates.extend(
            (
                Path("/Applications/Godot.app/Contents/MacOS/Godot"),
                Path.home() / "Applications/Godot.app/Contents/MacOS/Godot",
            )
        )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


__all__ = (
    "ValidatedSpeciesRuntimeCatalog",
    "build_species_runtime_catalog",
)
