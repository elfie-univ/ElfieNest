from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from infrastructure.godot.artifacts import web_build
from infrastructure.godot.artifacts.export_boundary import export_boundary_manifest
from infrastructure.godot.artifacts.web_build import (
    current_source_fingerprint,
    current_species_catalog_digest,
    patch_web_entry_for_lan_http,
    runtime_is_current,
)


def _write_runtime(directory: Path, fingerprint: str) -> None:
    directory.mkdir()
    files = {}
    for suffix in (".html", ".js", ".wasm", ".pck"):
        path = directory / f"elfienest{suffix}"
        path.write_bytes(b"runtime")
        files[path.name] = {
            "bytes": len(b"runtime"),
            "sha256": hashlib.sha256(b"runtime").hexdigest(),
        }
    (directory / "build-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "files": files,
                "source_fingerprint": fingerprint,
                "species_catalog_digest": current_species_catalog_digest(),
                "species_package_ids": ["dog", "fox"],
                "export_boundary": export_boundary_manifest(),
            }
        ),
        encoding="utf-8",
    )


def test_runtime_is_current_when_manifest_matches_source_fingerprint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    monkeypatch.setattr(
        "infrastructure.godot.artifacts.web_build.GODOT_PROJECT", project
    )
    output = tmp_path / "runtime"
    _write_runtime(output, current_source_fingerprint())

    assert runtime_is_current(output) is True


def test_runtime_is_stale_when_godot_source_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    scene = project / "main.tscn"
    scene.write_text('[node name="Nest"]\n', encoding="utf-8")
    monkeypatch.setattr(
        "infrastructure.godot.artifacts.web_build.GODOT_PROJECT", project
    )
    output = tmp_path / "runtime"
    _write_runtime(output, current_source_fingerprint())
    scene.write_text('[node name="ChangedNest"]\n', encoding="utf-8")

    assert runtime_is_current(output) is False


def test_patch_web_entry_for_lan_http_adds_scoped_godot_compatibility(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "elfienest.html"
    entry.write_text(
        '<script src="elfienest.js"></script>\n'
        "const GODOT_CONFIG = {};\n"
        "const GODOT_THREADS_ENABLED = false;\n"
        "\tconst missing = Engine.getMissingFeatures({\n"
        "\t\tthreads: GODOT_THREADS_ENABLED,\n"
        "\t});\n",
        encoding="utf-8",
    )

    patch_web_entry_for_lan_http(entry)
    patched = entry.read_text(encoding="utf-8")

    assert "elfienest:lan-http-compatibility" in patched
    assert "audioWorklet" in patched
    assert "!('audioWorklet' in window.AudioContext.prototype)" in patched
    assert "!window.AudioContext.prototype.audioWorklet" not in patched
    assert "addModule" in patched
    assert "window.location.protocol !== 'http:'" in patched
    assert (
        "feature === 'Secure Context - Check web server configuration (use HTTPS)'"
        in patched
    )
    assert ".filter((feature) =>" in patched

    patch_web_entry_for_lan_http(entry)
    assert entry.read_text(encoding="utf-8") == patched


def test_web_export_imports_before_species_validation_and_publishes_after_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[str] = []
    output = tmp_path / "runtime"

    def fake_export(*args, **kwargs):
        del args, kwargs
        events.append("export")
        entry = output.parent / ".runtime.staging" / "elfienest.html"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            "const GODOT_CONFIG = {};\n"
            "const GODOT_THREADS_ENABLED = false;\n"
            "\tconst missing = Engine.getMissingFeatures({\n"
            "\t\tthreads: GODOT_THREADS_ENABLED,\n"
            "\t});\n",
            encoding="utf-8",
        )
        for suffix in (".js", ".wasm", ".pck"):
            (entry.parent / f"elfienest{suffix}").write_bytes(b"runtime")
        return SimpleNamespace(
            exit_code=0,
            crashed=False,
            stdout="",
            stderr="",
        )

    def fake_validate(*args, **kwargs):
        del args, kwargs
        events.append("validate")
        return ("dog", "fox")

    monkeypatch.setattr(web_build, "run_headless", fake_export)
    monkeypatch.setattr(web_build, "validate_source_species_packages", fake_validate)

    assert (
        web_build._export_runtime_locked(
            output,
            Path("/fake/godot"),
            "4.7",
            "4.7",
            ("dog", "fox"),
            lambda **kwargs: None,
        )
        == 0
    )
    assert events == ["export", "validate"]
    assert (output / "build-manifest.json").is_file()
