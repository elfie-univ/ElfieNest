"""Run the Godot-owned species package validation script."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationResult,
)
from infrastructure.godot.runner import run_headless

_SPECIES_VALIDATION_SCRIPT = "scripts/test/test_species_catalog.gd"


def run_godot_species_validation(
    *,
    godot_binary: Path,
    godot_project: Path,
    timeout_seconds: float,
    godot_version: Optional[str] = None,
) -> GodotSpeciesValidationResult:
    """Run the Godot source-project contract through the script-owned boundary."""

    result = run_headless(
        godot_binary,
        godot_project,
        ("--script", _SPECIES_VALIDATION_SCRIPT),
        timeout_seconds=timeout_seconds,
        godot_version=godot_version,
        purpose="species-package-validation",
    )
    return GodotSpeciesValidationResult(
        result.exit_code,
        result.stdout,
        result.stderr,
        phase="species-validation",
    )


__all__ = ("run_godot_species_validation",)
