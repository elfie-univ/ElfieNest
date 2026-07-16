from __future__ import annotations

import json
from pathlib import Path

from elfienest.operations.godot_web import inspect_godot_web_bundle


def test_bundle_status_requires_all_runtime_artifacts(tmp_path: Path) -> None:
    for suffix in (".html", ".js", ".wasm"):
        (tmp_path / f"elfienest{suffix}").write_bytes(b"runtime")

    status = inspect_godot_web_bundle(tmp_path)

    assert status.ready is False
    assert ".pck" in status.missing
    assert "build-manifest.json" in status.missing


def test_bundle_status_reads_complete_manifest(tmp_path: Path) -> None:
    for suffix in (".html", ".js", ".wasm", ".pck"):
        (tmp_path / f"elfienest{suffix}").write_bytes(b"runtime")
    (tmp_path / "build-manifest.json").write_text(
        json.dumps({"godot_version": "4.6"}),
        encoding="utf-8",
    )

    status = inspect_godot_web_bundle(tmp_path)

    assert status.ready is True
    assert status.manifest["godot_version"] == "4.6"
