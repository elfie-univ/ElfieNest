"""Run the Godot-owned species package validation script."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationResult,
)
from infrastructure.godot.runner import run_headless

_SPECIES_VALIDATION_SCRIPT = "scripts/test/test_species_catalog.gd"
_PROJECT_IMPORT_PHASE = "project-import"
_SPECIES_VALIDATION_PHASE = "species-validation"


def _text_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return "" if value is None else str(value)


def _run_godot_phase(
    *,
    command: tuple[str, ...],
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
        phase=phase,
    )


def _join_output(*outputs: str) -> str:
    return "\n".join(output for output in outputs if output)


def run_godot_species_validation(
    *,
    godot_binary: Path,
    godot_project: Path,
    timeout_seconds: float,
) -> GodotSpeciesValidationResult:
    """Import the project, then run the Godot-owned species contract."""

    deadline = time.monotonic() + timeout_seconds
    import_result = _run_godot_phase(
        command=(
            str(godot_binary),
            "--headless",
            "--editor",
            "--path",
            str(godot_project),
            "--quit",
        ),
        godot_project=godot_project,
        timeout_seconds=max(0.001, deadline - time.monotonic()),
        phase=_PROJECT_IMPORT_PHASE,
    )
    if import_result.returncode != 0:
        return import_result

    validation_result = _run_godot_phase(
        command=(
            str(godot_binary),
            "--headless",
            "--path",
            str(godot_project),
            "--script",
            _SPECIES_VALIDATION_SCRIPT,
        ),
        godot_project=godot_project,
        timeout_seconds=max(0.001, deadline - time.monotonic()),
        phase=_SPECIES_VALIDATION_PHASE,
    )
    return GodotSpeciesValidationResult(
        validation_result.returncode,
        _join_output(import_result.stdout, validation_result.stdout),
        _join_output(import_result.stderr, validation_result.stderr),
        phase=validation_result.phase,
    )


__all__ = ("run_godot_species_validation",)
