"""Build-time gate joining the Python species catalog to Godot packages."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from infrastructure.persistence.configuration.species import load_species_catalog


class SpeciesPackageValidationError(RuntimeError):
    """The configuration and Godot species packages cannot be shipped together."""

    def __init__(
        self,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
        phase: str = "species-validation",
    ) -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr
        self.phase = phase


@dataclass(frozen=True)
class GodotSpeciesValidationResult:
    """Result returned by the Bootstrap-owned Godot validation runner."""

    returncode: int
    stdout: str
    stderr: str
    phase: str = "species-validation"


class GodotSpeciesValidationRunner(Protocol):
    """Narrow process boundary for the Godot-owned package validation script."""

    def __call__(
        self,
        *,
        godot_binary: Path,
        godot_project: Path,
        timeout_seconds: float,
        godot_version: Optional[str] = None,
    ) -> GodotSpeciesValidationResult: ...


_CATALOG_MARKER = re.compile(r"^SPECIES_CATALOG_IDS:(.+)$", re.MULTILINE)
_EXCLUDED_CHARACTER_DIRECTORIES = {"animation", "shared", "tools"}


def source_species_package_ids(
    *,
    config_root: Path,
    godot_project: Path,
) -> tuple[str, ...]:
    """Validate source manifests and return the packages expected at runtime."""

    config_root = config_root.resolve()
    godot_project = godot_project.resolve()
    catalog = load_species_catalog(root=config_root)
    definitions = tuple(
        definition for definition in catalog.definitions if definition.resolvable
    )
    expected_packages = tuple(definition.godot_package_id for definition in definitions)
    if len(set(expected_packages)) != len(expected_packages):
        raise SpeciesPackageValidationError(
            "species-config-godot-package-ids-duplicate"
        )

    characters_root = godot_project / "characters"
    if not characters_root.is_dir():
        raise SpeciesPackageValidationError(
            f"godot-characters-root-missing path={characters_root}"
        )
    manifest_packages: set[str] = set()
    for definition in definitions:
        if definition.species_id != definition.godot_package_id:
            raise SpeciesPackageValidationError(
                "species-config-godot-id-mismatch "
                f"species_id={definition.species_id} "
                f"godot_package_id={definition.godot_package_id}"
            )
        package_root = characters_root / definition.godot_package_id
        manifest_path = package_root / "species_manifest.json"
        if not manifest_path.is_file():
            raise SpeciesPackageValidationError(
                f"godot-species-manifest-missing species_id={definition.species_id}"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SpeciesPackageValidationError(
                f"godot-species-manifest-invalid species_id={definition.species_id}"
            ) from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("species_id") != definition.species_id
        ):
            raise SpeciesPackageValidationError(
                f"godot-species-manifest-id-mismatch species_id={definition.species_id}"
            )
        for key in ("scene_file", "model_file"):
            asset_name = manifest.get(key)
            if (
                not isinstance(asset_name, str)
                or not (package_root / asset_name).is_file()
            ):
                raise SpeciesPackageValidationError(
                    f"godot-species-asset-missing species_id={definition.species_id} key={key}"
                )
        manifest_packages.add(definition.godot_package_id)

    actual_manifest_packages = {
        path.name
        for path in characters_root.iterdir()
        if path.is_dir()
        and path.name not in _EXCLUDED_CHARACTER_DIRECTORIES
        and (path / "species_manifest.json").is_file()
    }
    if actual_manifest_packages != manifest_packages:
        raise SpeciesPackageValidationError(
            "godot-species-package-set-mismatch "
            f"expected={sorted(manifest_packages)} "
            f"actual={sorted(actual_manifest_packages)}"
        )

    return tuple(sorted(manifest_packages))


def validate_source_species_packages(
    *,
    config_root: Path,
    godot_project: Path,
    godot_runner: GodotSpeciesValidationRunner,
    godot_binary: Path | None = None,
    timeout_seconds: float = 120.0,
    godot_version: Optional[str] = None,
) -> tuple[str, ...]:
    """Validate package links through an injected Godot process boundary."""

    manifest_packages = source_species_package_ids(
        config_root=config_root,
        godot_project=godot_project,
    )

    binary = godot_binary or _find_godot_binary()
    if binary is None:
        raise SpeciesPackageValidationError("godot-binary-missing")
    if godot_version is None:
        result = godot_runner(
            godot_binary=binary,
            godot_project=godot_project,
            timeout_seconds=timeout_seconds,
        )
    else:
        result = godot_runner(
            godot_binary=binary,
            godot_project=godot_project,
            timeout_seconds=timeout_seconds,
            godot_version=godot_version,
        )
    output = f"{result.stdout}\n{result.stderr}"
    diagnostic_kwargs = {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "phase": result.phase,
    }
    if result.returncode != 0:
        raise SpeciesPackageValidationError(
            f"godot-species-validation-failed exit={result.returncode}",
            **diagnostic_kwargs,
        )
    match = _CATALOG_MARKER.search(output)
    if match is None:
        raise SpeciesPackageValidationError(
            "godot-species-validation-marker-missing",
            **diagnostic_kwargs,
        )
    try:
        discovered = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise SpeciesPackageValidationError(
            "godot-species-validation-marker-invalid",
            **diagnostic_kwargs,
        ) from error
    if not isinstance(discovered, list) or any(
        not isinstance(item, str) for item in discovered
    ):
        raise SpeciesPackageValidationError(
            "godot-species-validation-ids-invalid",
            **diagnostic_kwargs,
        )
    if set(discovered) != set(manifest_packages):
        raise SpeciesPackageValidationError(
            "godot-species-discovery-set-mismatch "
            f"expected={sorted(manifest_packages)} actual={sorted(discovered)}",
            **diagnostic_kwargs,
        )
    return manifest_packages


def _find_godot_binary() -> Path | None:
    binary = shutil.which("godot")
    return None if binary is None else Path(binary)


__all__ = (
    "GodotSpeciesValidationResult",
    "GodotSpeciesValidationRunner",
    "SpeciesPackageValidationError",
    "source_species_package_ids",
    "validate_source_species_packages",
)
