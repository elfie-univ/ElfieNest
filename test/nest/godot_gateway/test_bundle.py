from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pytest import MonkeyPatch

from nest.godot_gateway.bundle import inspect_godot_web_bundle


def test_bundle_status_requires_all_runtime_artifacts(tmp_path: Path) -> None:
    for suffix in (".html", ".js", ".wasm"):
        (tmp_path / f"elfienest{suffix}").write_bytes(b"runtime")

    status = inspect_godot_web_bundle(tmp_path)

    assert status.ready is False
    assert ".pck" in status.missing
    assert "build-manifest.json" in status.missing


def test_bundle_status_uses_the_packaged_runtime_directory_from_environment(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an installed Core receives the Godot bundle directory from Desktop.
    monkeypatch.setenv("ELFIENEST_GODOT_WEB_DIR", str(tmp_path))

    # When: it performs its normal runtime inspection without a source-tree argument.
    status = inspect_godot_web_bundle()

    # Then: package resources—not PyInstaller's temporary source extraction—are inspected.
    assert status.directory == tmp_path


def test_bundle_status_reads_complete_manifest(tmp_path: Path) -> None:
    for suffix in (".html", ".js", ".wasm", ".pck"):
        (tmp_path / f"elfienest{suffix}").write_bytes(b"runtime")
    files = {
        f"elfienest{suffix}": {
            "bytes": len(b"runtime"),
            "sha256": hashlib.sha256(b"runtime").hexdigest(),
        }
        for suffix in (".html", ".js", ".wasm", ".pck")
    }
    (tmp_path / "build-manifest.json").write_text(
        json.dumps({"godot_version": "4.6", "files": files}),
        encoding="utf-8",
    )

    status = inspect_godot_web_bundle(tmp_path)

    assert status.ready is True
    assert status.manifest["godot_version"] == "4.6"


def test_bundle_status_rejects_tampered_runtime_file(tmp_path: Path) -> None:
    # Given
    for suffix in (".html", ".js", ".wasm", ".pck"):
        (tmp_path / f"elfienest{suffix}").write_bytes(b"runtime")
    files = {
        f"elfienest{suffix}": {
            "bytes": len(b"runtime"),
            "sha256": hashlib.sha256(b"runtime").hexdigest(),
        }
        for suffix in (".html", ".js", ".wasm", ".pck")
    }
    (tmp_path / "build-manifest.json").write_text(
        json.dumps({"files": files}),
        encoding="utf-8",
    )
    (tmp_path / "elfienest.pck").write_bytes(b"tampered")

    # When
    status = inspect_godot_web_bundle(tmp_path)

    # Then
    assert status.ready is False
    assert any("sha256" in error for error in status.integrity_errors)
