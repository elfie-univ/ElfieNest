from __future__ import annotations

import subprocess
from pathlib import Path

from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationResult,
)
from scripts import godot_species_validation


def test_imports_project_before_running_species_contract(monkeypatch) -> None:
    calls: list[tuple[tuple[str, ...], float]] = []

    def fake_run(
        command: tuple[str, ...],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
        timeout: float,
    ):
        assert cwd == Path("godot_project")
        assert capture_output is True
        assert text is True
        assert check is False
        calls.append((command, timeout))
        if len(calls) == 1:
            return type(
                "CompletedProcess",
                (),
                {"returncode": 0, "stdout": "project imported\n", "stderr": ""},
            )()
        return type(
            "CompletedProcess",
            (),
            {
                "returncode": 0,
                "stdout": 'SPECIES_CATALOG_IDS:["dog","fox"]\n',
                "stderr": "",
            },
        )()

    monkeypatch.setattr(godot_species_validation.subprocess, "run", fake_run)

    result = godot_species_validation.run_godot_species_validation(
        godot_binary=Path("godot"),
        godot_project=Path("godot_project"),
        timeout_seconds=10.0,
    )

    assert result == GodotSpeciesValidationResult(
        0,
        'project imported\n\nSPECIES_CATALOG_IDS:["dog","fox"]\n',
        "",
    )
    assert calls[0][0] == (
        "godot",
        "--headless",
        "--editor",
        "--path",
        "godot_project",
        "--quit",
    )
    assert calls[1][0] == (
        "godot",
        "--headless",
        "--path",
        "godot_project",
        "--script",
        "scripts/test/test_species_catalog.gd",
    )


def test_import_failure_is_reported_without_running_species_contract(
    monkeypatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **kwargs):
        del kwargs
        calls.append(command)
        return type(
            "CompletedProcess",
            (),
            {
                "returncode": 1,
                "stdout": "import stdout\n",
                "stderr": "import stderr\n",
            },
        )()

    monkeypatch.setattr(godot_species_validation.subprocess, "run", fake_run)

    result = godot_species_validation.run_godot_species_validation(
        godot_binary=Path("godot"),
        godot_project=Path("godot_project"),
        timeout_seconds=10.0,
    )

    assert result.returncode == 1
    assert result.phase == "project-import"
    assert result.stdout == "import stdout\n"
    assert result.stderr == "import stderr\n"
    assert len(calls) == 1


def test_timeout_preserves_partial_godot_output(monkeypatch) -> None:
    def fake_run(command: tuple[str, ...], **kwargs):
        del kwargs
        raise subprocess.TimeoutExpired(
            command,
            1.0,
            output="partial stdout\n",
            stderr="partial stderr\n",
        )

    monkeypatch.setattr(godot_species_validation.subprocess, "run", fake_run)

    result = godot_species_validation.run_godot_species_validation(
        godot_binary=Path("godot"),
        godot_project=Path("godot_project"),
        timeout_seconds=10.0,
    )

    assert result.returncode == 1
    assert result.phase == "project-import"
    assert result.stdout == "partial stdout\n"
    assert result.stderr == "partial stderr\n"
