"""Source changes invalidate the formal preview, including unchanged timestamps."""

import importlib
import json
import os
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "resource",
    [
        "furniture/shared/bedroom/chair.glb",
        "furniture/sets/bedroom/bedroom-set-a.scn",
        "assembly/estate.tscn",
    ],
)
def test_changed_resource_requires_asset_rebuild(tmp_path, monkeypatch, resource):
    tools = Path(__file__).resolve().parents[2] / "godot_project/tools"
    monkeypatch.syspath_prepend(str(tools))
    review = importlib.import_module("publish_static_asset_review")
    project = tmp_path / "godot_project"
    nest = project / "nest"
    web = tmp_path / "web"
    web.mkdir()
    monkeypatch.setattr(review, "ROOT", tmp_path)
    monkeypatch.setattr(review, "GODOT", project)
    monkeypatch.setattr(review, "NEST", nest)
    monkeypatch.setattr(review, "WEB", web)
    publisher = project / "tools/publish_static_asset_review.py"
    monkeypatch.setattr(review, "__file__", str(publisher))
    index = nest / "assembly/asset-index.json"
    monkeypatch.setattr(review, "NEST_INDEX", index)
    for path in [
        project / "project.godot",
        nest / "nest.tscn",
        publisher,
        project / "tools/pack_nest_assets.gd",
        project / "tools/static_asset_review.gd",
        project / "tools/review_asset_sizes.py",
        nest / resource,
        index,
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    (web / "nest-assets.pck").write_bytes(b"pack")
    (web / "elfienest.html").write_text("shell")
    (web / "nest-assets.html").write_text("viewer")
    (web / "nest-assets.json").write_text(
        json.dumps(
            {
                "sourceFingerprint": review.nest_source_fingerprint(),
                "shellSha256": review.sha256(web / "elfienest.html"),
                "sha256": review.sha256(web / "nest-assets.pck"),
                "packBytes": 4,
            }
        )
    )
    assert review.nest_assets_current()
    source = nest / resource
    authoring = source.parent / "source"
    authoring.mkdir()
    (authoring / ".gdignore").touch()
    (authoring / "editable.blend").write_bytes(b"Blender changes")
    (authoring / "exchange.glb").write_bytes(b"not a runtime asset")
    assert review.nest_assets_current()

    stat = source.stat()
    source.write_text("[]")
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert not review.nest_assets_current()
