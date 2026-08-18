"""Run the Godot-owned species package validation script."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationResult,
)

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
    phase: str,
) -> GodotSpeciesValidationResult:
    try:
        result = subprocess.run(
            command,
            cwd=godot_project,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        return GodotSpeciesValidationResult(
            1,
            _text_output(error.stdout),
            _text_output(error.stderr) or str(error),
            phase=phase,
        )
    except OSError as error:
        return GodotSpeciesValidationResult(
            1,
            "",
            str(error),
            phase=phase,
        )
    return GodotSpeciesValidationResult(
        result.returncode,
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
