from __future__ import annotations

import json
from pathlib import Path

from scripts import build_godot_web


def _write_bundle(directory: Path, source_digest: str) -> None:
    directory.mkdir()
    for suffix in (".html", ".js", ".wasm", ".pck"):
        (directory / f"elfienest{suffix}").write_bytes(b"bundle")
    (directory / "build-manifest.json").write_text(
        json.dumps({"source_digest": source_digest}), encoding="utf-8"
    )


def test_bundle_is_current_only_when_it_matches_godot_source(tmp_path: Path) -> None:
    # Given: an exported bundle that records the present Godot project sources.
    project = tmp_path / "godot_project"
    project.mkdir()
    scene = project / "main.tscn"
    scene.write_text("[gd_scene]", encoding="utf-8")
    bundle = tmp_path / "godot-web"
    _write_bundle(bundle, build_godot_web.source_digest(project))

    # When / Then: the exact sources are current, but a source edit invalidates it.
    assert build_godot_web.bundle_is_current(bundle, project) is True
    scene.write_text('[gd_scene]\n[node name="Main"]', encoding="utf-8")
    assert build_godot_web.bundle_is_current(bundle, project) is False


def test_source_digest_ignores_godot_import_cache_and_generated_uids(
    tmp_path: Path,
) -> None:
    # Given: stable Godot source plus generated import cache metadata.
    project = tmp_path / "godot_project"
    cache = project / ".godot"
    cache.mkdir(parents=True)
    (project / "actor.gd").write_text("extends Node3D", encoding="utf-8")
    (project / "actor.gd.uid").write_text("uid://generated", encoding="utf-8")
    (cache / "cache.bin").write_bytes(b"cache")

    # When: only generated files change.
    before = build_godot_web.source_digest(project)
    (project / "actor.gd.uid").write_text("uid://changed", encoding="utf-8")
    (cache / "cache.bin").write_bytes(b"changed")

    # Then: a Lab launch does not rebuild merely because Godot refreshed cache data.
    assert build_godot_web.source_digest(project) == before
