from __future__ import annotations

import hashlib
import json
from pathlib import Path

from infrastructure.godot.artifacts.web_build import (
    current_source_fingerprint,
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
