"""Linux Dedicated Godot bundle contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from infrastructure.godot.artifacts.export_boundary import export_boundary_manifest
from scripts.build_godot_dedicated import (
    current_species_catalog_digest,
    runtime_is_current,
)


def _write_bundle(directory: Path, fingerprint: str) -> None:
    directory.mkdir()
    runtime = directory / "ElfieNestRuntime"
    runtime.write_bytes(b"dedicated-runtime")
    runtime.chmod(0o755)
    metadata = {
        runtime.name: {
            "bytes": runtime.stat().st_size,
            "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
        }
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "files": metadata,
                "source_fingerprint": fingerprint,
                "species_catalog_digest": current_species_catalog_digest(),
                "species_package_ids": ["dog", "fox"],
                "export_boundary": export_boundary_manifest(),
            }
        ),
        encoding="utf-8",
    )


def test_dedicated_runtime_is_current_with_only_linux_executable(
    tmp_path: Path, monkeypatch
) -> None:
    # Given: a fingerprinted Linux x64 executable-only bundle.
    project = tmp_path / "godot_project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setattr("scripts.build_godot_dedicated.GODOT_PROJECT", project)
    output = tmp_path / "runtime"

    from scripts.build_godot_dedicated import current_source_fingerprint

    _write_bundle(output, current_source_fingerprint())

    # When / Then: it is accepted without any HTML, JS, Wasm, or PCK payload.
    assert runtime_is_current(output) is True


def test_developer_entrypoint_exposes_the_dedicated_builder() -> None:
    # Given: the contributor command router.
    router = (Path(__file__).resolve().parents[2] / "developer.sh").read_text(
        encoding="utf-8"
    )

    # When / Then: it dispatches directly to the constrained dedicated builder.
    assert '"${1:-}" == "build-godot-dedicated"' in router
    assert "scripts/build_godot_dedicated.py" in router


def test_dedicated_builder_is_importable_when_executed_as_a_script() -> None:
    # Given: the entrypoint is invoked exactly as developer.sh invokes it.
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "build_godot_dedicated.py"
    )

    # When: the builder checks a missing temporary bundle.
    result = subprocess.run(
        [sys.executable, str(script), "--check", "--output", "/tmp/missing-runtime"],
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: it reaches its bundle check rather than failing to import its helpers.
    assert result.returncode == 1
    assert "Linux Dedicated Runtime is incomplete" in result.stdout
