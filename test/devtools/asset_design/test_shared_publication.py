"""Shared parts and storage revisions publish without changing adoption."""

import hashlib
import json

import pytest

from devtools.asset_design.catalog_store import read_catalog, save_catalog
from devtools.asset_design.design_catalog import GROUPS
from devtools.asset_design.glb_resources import (
    encode_glb,
    read_glb,
    relocate_glb,
)
from devtools.asset_design.object_assets import publish_object
from devtools.asset_design.object_content import content_digest
from devtools.asset_design.object_glb import extract_glb
from test.devtools.asset_design.test_glb_resources import fixture


def prepare(root):
    original, model, doc, resources = fixture(root)
    identifier = "part:example_plant"
    folder = root / "furniture/example_plant"
    source = folder / "source/model.glb"
    source.parent.mkdir(parents=True)
    doc["nodes"][0]["extras"]["assembly"] = "example_plant"
    doc["nodes"].append(
        {"mesh": 0, "extras": {"reference": True}, "translation": [9, 0, 0]}
    )
    doc["scenes"][0]["nodes"].append(1)
    model.write_bytes(encode_glb(doc))
    source.write_bytes(relocate_glb(model, source, root=root))
    build = {
        "object": identifier,
        "placements": {},
        "instanceCount": 1,
        "description": "已确认布置引用 10 处。",
        "reuse": {"instances": 10, "objects": ["layout:central:1"]},
    }
    (source.parent / "build.json").write_text(json.dumps(build))
    (root / "catalog.json").write_text(json.dumps({"assets": []}))
    return identifier, source, build, resources, original


def test_new_shared_part_registers_sources_and_unique_dependencies(tmp_path):
    identifier, source, build, resources, _ = prepare(tmp_path)
    result = publish_object(tmp_path, identifier, label="公共盆栽")
    assert result["changed"]
    rows = read_catalog(tmp_path)["assets"]
    assert len(rows) == 1
    row = rows[0]
    assert row["designObject"]["group"] in GROUPS
    assert row["category"] == "kit"
    assert row["designObject"] == {
        "id": identifier,
        "label": "公共盆栽",
        "group": "kit",
        "space": "estate",
        "module": "",
        "floor": "",
        "collection": "part:shared_library",
        "collectionLabel": "公共资产库",
    }
    assert row["description"] == build["description"]
    assert row["designVersion"]["reuse"] == build["reuse"]
    files = {entry["path"]: entry["kind"] for entry in row["files"]}
    assert len(files) == len(row["files"]) == 5
    assert files[source.relative_to(tmp_path).as_posix()] == "source"
    assert (
        files[source.with_name("build.json").relative_to(tmp_path).as_posix()] == "data"
    )
    for resource in resources:
        assert files[resource.relative_to(tmp_path).as_posix()] == (
            "data" if resource.suffix == ".bin" else "texture"
        )
    published, binary = read_glb(tmp_path / result["file"])
    assert not binary
    assert published["buffers"][0]["uri"]
    assert len(published["nodes"]) == 2
    assert published["nodes"][1]["extras"]["reference"]
    assert content_digest(tmp_path, result["file"], [0]) == content_digest(
        tmp_path, source.relative_to(tmp_path), [0]
    )


def test_storage_revision_keeps_semantic_digest_and_confirmations(tmp_path):
    identifier, source, _, _, _ = prepare(tmp_path)
    first = publish_object(tmp_path, identifier, label="公共盆栽")
    catalog_path = tmp_path / "catalog.json"
    catalog = read_catalog(catalog_path.parent)
    row = catalog["assets"][0]
    target = tmp_path / first["file"]
    target.write_bytes(extract_glb(source, [0])[0])
    # The old revision is a semantically identical embedded GLB.
    row["designVersion"]["digest"] = hashlib.sha256(target.read_bytes()).hexdigest()
    save_catalog(catalog_path.parent, catalog)
    state = b'{"current":{"part:example_plant":{"version":"first"}},"history":[]}'
    (tmp_path / "adoptions.json").write_bytes(state)
    assert publish_object(tmp_path, identifier)["changed"] is False
    second = publish_object(tmp_path, identifier, storage_revision=True)
    assert second["changed"]
    rows = read_catalog(catalog_path.parent)["assets"]
    assert len(rows) == 2
    assert rows[0] == row
    assert (
        rows[1]["designVersion"]["contentDigest"]
        == row["designVersion"]["contentDigest"]
    )
    assert (tmp_path / "adoptions.json").read_bytes() == state
    # Repeated storage publishing must not manufacture more revisions.
    assert (
        publish_object(tmp_path, identifier, storage_revision=True)["changed"] is False
    )


def test_unknown_objects_require_explicit_new_part_label(tmp_path):
    identifier, _, _, _, _ = prepare(tmp_path)
    for requested, kwargs in ((identifier, {}), ("layout:unknown", {"label": "无效"})):
        with pytest.raises(ValueError, match="Unknown independent object"):
            publish_object(tmp_path, requested, **kwargs)
    assert read_catalog(tmp_path)["assets"] == []


def test_tampered_resource_cannot_create_catalog_revision(tmp_path):
    identifier, _, _, resources, _ = prepare(tmp_path)
    before = (tmp_path / "catalog.json").read_bytes()
    resources[0].write_bytes(b"tampered geometry")
    with pytest.raises(ValueError, match="SHA256"):
        publish_object(tmp_path, identifier, label="公共盆栽")
    assert (tmp_path / "catalog.json").read_bytes() == before


def test_reuse_placements_are_saved_separately_from_the_catalog(tmp_path):
    identifier, source, build, _, _ = prepare(tmp_path)
    build["reuse"] = {
        "identity": "assembly",
        "sourceReferences": 2,
        "estateReferences": 16,
        "occurrences": [
            {
                "sceneObject": "layout:pod",
                "placement": {
                    "worldTransforms": [{"node": 0, "matrix": [[1, 0], [0, 1]]}]
                },
            }
        ],
        "resources": ["shared.bin"],
    }
    source.with_name("build.json").write_text(json.dumps(build))
    publish_object(tmp_path, identifier, label="公共盆栽")
    row = read_catalog(tmp_path)["assets"][0]
    summary = row["designVersion"]["reuse"]
    assert summary["estateReferences"] == 16
    assert "occurrences" not in summary and "resources" not in summary
    details = tmp_path / summary["details"]
    assert json.loads(details.read_text()) == build["reuse"]
    assert any(f["path"] == summary["details"] for f in row["files"])
