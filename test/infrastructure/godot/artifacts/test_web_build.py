from __future__ import annotations

import hashlib
import json
import os
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

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
                "species_package_ids": ["myelle", "saevi", "tovren"],
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


@pytest.mark.parametrize("suffix", [".glb", ".instances.bin"])
def test_export_rejects_unresolved_lfs_assets_before_starting_godot(
    tmp_path: Path, monkeypatch, capsys, suffix: str
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    asset = project / ("estate" + suffix)
    asset.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 100\n"
    )
    monkeypatch.setattr(web_build, "GODOT_PROJECT", project)
    monkeypatch.setattr(
        web_build,
        "_find_godot",
        lambda *_: pytest.fail("Unresolved assets must fail before Godot starts"),
    )
    assert (
        web_build._export_runtime(tmp_path / "runtime", None, False, godot_runner=None)
        == 1
    )
    assert "git lfs pull" in capsys.readouterr().out


def test_resolved_binary_assets_are_not_lfs_pointers(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "estate.glb").write_bytes(b"glTF" + bytes(256))
    monkeypatch.setattr(web_build, "GODOT_PROJECT", tmp_path)
    assert web_build._unresolved_lfs_assets() == []


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
    assert "elfienest:webgl-canvas-capture" in patched
    assert "preserveDrawingBuffer: true" in patched
    assert "powerPreference: 'high-performance'" in patched

    # A substring check alone accepts JavaScript emitted as visible body text.
    class ScriptCollector(HTMLParser):
        in_script = False

        def __init__(self) -> None:
            super().__init__()
            self.scripts: list[str] = []

        def handle_starttag(self, tag, attrs) -> None:
            if tag == "script":
                self.in_script = True

        def handle_endtag(self, tag) -> None:
            if tag == "script":
                self.in_script = False

        def handle_data(self, data) -> None:
            if self.in_script:
                self.scripts.append(data)

    parsed = ScriptCollector()
    parsed.feed(patched)
    assert any("elfienest:webgl-canvas-capture" in script for script in parsed.scripts)
    assert patched.index("patchGodotCanvasCapture") < patched.index(
        '<script src="elfienest.js">'
    )
    assert "window.location.protocol !== 'http:'" in patched
    assert (
        "feature === 'Secure Context - Check web server configuration (use HTTPS)'"
        in patched
    )
    assert ".filter((feature) =>" in patched

    patch_web_entry_for_lan_http(entry)
    assert entry.read_text(encoding="utf-8") == patched


def test_capture_patch_revision_invalidates_existing_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    monkeypatch.setattr(web_build, "GODOT_PROJECT", project)
    current_revision = web_build.CANVAS_CAPTURE_VERSION
    monkeypatch.setattr(web_build, "CANVAS_CAPTURE_VERSION", "canvas-capture-v1")
    old_fingerprint = current_source_fingerprint()
    monkeypatch.setattr(web_build, "CANVAS_CAPTURE_VERSION", current_revision)
    assert current_source_fingerprint() != old_fingerprint


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
            '<script src="elfienest.js"></script>\n'
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
        return ("tovren", "saevi")

    monkeypatch.setattr(web_build, "run_headless", fake_export)
    monkeypatch.setattr(web_build, "validate_source_species_packages", fake_validate)

    assert (
        web_build._export_runtime_locked(
            output,
            Path("/fake/godot"),
            "4.7",
            "4.7",
            ("tovren", "saevi"),
            lambda **kwargs: None,
        )
        == 0
    )
    assert events == ["export", "validate"]
    assert (output / "build-manifest.json").is_file()


def test_build_lock_recovers_an_unowned_stale_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "runtime"
    lock_path = tmp_path / ".runtime.lock"
    lock_path.write_text("7982", encoding="ascii")
    ticks = iter((0.0, 121.0))
    monkeypatch.setattr(web_build.time, "monotonic", ticks.__next__)

    with web_build._build_lock(output):
        assert lock_path.read_text(encoding="ascii") == str(os.getpid())


def test_build_lock_still_rejects_a_concurrent_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "runtime"

    with web_build._build_lock(output):
        ticks = iter((0.0, 121.0))
        monkeypatch.setattr(web_build.time, "monotonic", ticks.__next__)
        with pytest.raises(RuntimeError, match="build lock timeout"):
            with web_build._build_lock(output):
                pass
