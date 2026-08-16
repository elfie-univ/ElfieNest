"""Run the Godot-owned species package validation script."""

from __future__ import annotations

import subprocess
from pathlib import Path

from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationResult,
)

_SPECIES_VALIDATION_SCRIPT = "scripts/test/test_species_catalog.gd"


def run_godot_species_validation(
    *,
    godot_binary: Path,
    godot_project: Path,
    timeout_seconds: float,
) -> GodotSpeciesValidationResult:
    """Run the Godot source-project contract through the script-owned boundary."""

    command = (
        str(godot_binary),
        "--headless",
        "--path",
        str(godot_project),
        "--script",
        _SPECIES_VALIDATION_SCRIPT,
    )
    try:
        result = subprocess.run(
            command,
            cwd=godot_project,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return GodotSpeciesValidationResult(1, "", str(error))
    return GodotSpeciesValidationResult(
        result.returncode,
        result.stdout,
        result.stderr,
    )


__all__ = ("run_godot_species_validation",)
