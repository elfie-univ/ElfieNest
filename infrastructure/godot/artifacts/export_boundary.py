"""Single source of truth for Godot source trees excluded from exports."""

from __future__ import annotations

from os import walk
from pathlib import Path
from typing import Final, Iterator, Tuple

GODOT_EXPORT_EXCLUDED_PATHS: Final[Tuple[str, ...]] = (
    "test/*",
    "tools/*",
    "characters/tools/*",
    "characters/tovren/source/*",
    "characters/saevi/source/*",
    # Split assemblies are runtime inputs; the retired merged entry is excluded.
    "nest/estate/ElfieNest-complete-final*",
    "nest/estate/estate.tscn",
    "nest/estate/estate_complete_final.gd",
    "nest/estate/estate_outdoor_lighting.scn",
)

GODOT_EXPORT_EXCLUDE_FILTER: Final[str] = ",".join(GODOT_EXPORT_EXCLUDED_PATHS)

# These resources are deliberately kept in source control for authoring or
# reference work.  They are not runtime inputs and must never be exported.
GODOT_AUTHORING_ONLY_PATHS: Final[Tuple[str, ...]] = (
    "characters/saevi/source",
    "characters/tools",
    "tools/nest_authoring",
)
GODOT_AUTHORING_ONLY_FILES: Final[Tuple[str, ...]] = ()


def runtime_source_files(root: Path) -> Iterator[Path]:
    """Walk the Godot source tree without entering authoring-only directories."""
    for directory, children, names in walk(root):
        parent = Path(directory)
        if (
            ".gdignore" in names
            or parent.relative_to(root).as_posix() in GODOT_AUTHORING_ONLY_PATHS
        ):
            children.clear()
            continue
        if ".godot" in children:
            children.remove(".godot")
        for name in names:
            path = parent / name
            if path.is_file() and path.suffix not in {".import", ".tmp"}:
                yield path


def export_boundary_manifest() -> dict[str, object]:
    """Return JSON-safe provenance for generated Runtime build manifests."""
    return {
        "filter": "all_resources",
        "excluded_paths": list(GODOT_EXPORT_EXCLUDED_PATHS),
        "authoring_only_paths": list(GODOT_AUTHORING_ONLY_PATHS),
        "authoring_only_files": list(GODOT_AUTHORING_ONLY_FILES),
    }


__all__ = (
    "GODOT_AUTHORING_ONLY_PATHS",
    "GODOT_AUTHORING_ONLY_FILES",
    "GODOT_EXPORT_EXCLUDED_PATHS",
    "GODOT_EXPORT_EXCLUDE_FILTER",
    "export_boundary_manifest",
    "runtime_source_files",
)
