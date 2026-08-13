from __future__ import annotations

import hashlib
import json
from pathlib import Path

from infrastructure.godot.artifacts.web_build import (
    current_source_fingerprint,
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
        json.dumps({"files": files, "source_fingerprint": fingerprint}),
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
        'const GODOT_CONFIG = {};\n'
        'const GODOT_THREADS_ENABLED = false;\n'
        '\tconst missing = Engine.getMissingFeatures({\n'
        '\t\tthreads: GODOT_THREADS_ENABLED,\n'
        '\t});\n',
        encoding="utf-8",
    )

    patch_web_entry_for_lan_http(entry)
    patched = entry.read_text(encoding="utf-8")

    assert "elfienest:lan-http-compatibility" in patched
    assert "audioWorklet" in patched
    assert "addModule" in patched
    assert "window.location.protocol !== 'http:'" in patched
    assert "feature === 'Secure Context - Check web server configuration (use HTTPS)'" in patched
    assert ".filter((feature) =>" in patched

    patch_web_entry_for_lan_http(entry)
    assert entry.read_text(encoding="utf-8") == patched
