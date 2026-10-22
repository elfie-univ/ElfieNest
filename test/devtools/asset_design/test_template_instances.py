"""Dynamic furniture instances resolve one registered mother, never scene copies."""

import copy
import json

import pytest
from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import read_catalog
from devtools.asset_design.glb_resources import encode_glb, read_glb
from devtools.asset_design.object_assets import publish_object, split_assets
from devtools.asset_design.object_content import content_digest
from test.devtools.asset_design.test_design import confirm, open_scene, setup


def prepare(root):
    setup(root)
    split_assets(root)
    folder = root / "furniture/common_chair/source"
    folder.mkdir(parents=True)
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {
                "name": "seat",
                "mesh": 0,
                "extras": {"assembly": "common_chair", "furniture": True},
            }
        ],
        "meshes": [{"primitives": [{"attributes": {}}]}],
    }
    (folder / "model.glb").write_bytes(encode_glb(doc))
    (folder / "build.json").write_text(
        json.dumps({"placements": {}, "instanceCount": 0})
    )
    publish_object(root, "part:common_chair", label="Common chair")
    host = root / "layouts/pod_bedroom/source/model.glb"
    doc, binary = read_glb(host)
    doc["materials"] = [{"pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}]
    doc["extras"] = {
        "templateInstances": [
            {
                "id": "chair-1",
                "object": "part:common_chair",
                "bindings": [
                    {
                        "node": 0,
                        "nodeName": "seat",
                        "sourceNode": 0,
                        "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 3, 0, 0, 1],
                        "materials": [0],
                        "properties": {"furniture": True},
                    }
                ],
            }
        ]
    }
    host.write_bytes(encode_glb(doc, binary))
    return host, folder


def test_reference_material_and_placement_affect_host_content(tmp_path):
    host, _ = prepare(tmp_path)
    relative = host.relative_to(tmp_path)
    original = content_digest(tmp_path, relative, [])
    doc, binary = read_glb(host)
    changed = copy.deepcopy(doc)
    changed["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] = [0, 1, 0, 1]
    host.write_bytes(encode_glb(changed, binary))
    assert content_digest(tmp_path, relative, []) != original
    changed = copy.deepcopy(doc)
    changed["extras"]["templateInstances"][0]["bindings"][0]["matrix"][12] = 9
    host.write_bytes(encode_glb(changed, binary))
    assert content_digest(tmp_path, relative, []) != original


@pytest.mark.parametrize(
    "field,value",
    [("object", "part:missing"), ("node", 99), ("nodeName", "wrong-seat")],
)
def test_invalid_mother_or_binding_fails_closed(tmp_path, field, value):
    host, _ = prepare(tmp_path)
    doc, binary = read_glb(host)
    instance = doc["extras"]["templateInstances"][0]
    (instance if field == "object" else instance["bindings"][0])[field] = value
    host.write_bytes(encode_glb(doc, binary))
    publish_object(tmp_path, "layout:pod")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "part:common_chair")).status_code == 200
        )
        response = client.get(
            "/assets/design/design/scene", params={"object": "layout:pod"}
        )
        assert response.status_code == 409


def test_fitted_reference_only_change_does_not_publish_revision(tmp_path):
    setup(tmp_path)
    split_assets(tmp_path)
    build = tmp_path / "buildings/pod/source/build.json"
    metadata = json.loads(build.read_text())
    metadata["previewReferences"] = [
        {"object": "layout:pod", "version": "layout_pod_v002"}
    ]
    build.write_text(json.dumps(metadata))
    assert not publish_object(tmp_path, "building:pod")["changed"]
    assert all(
        "previewReferences" not in a["designVersion"]
        for a in read_catalog(tmp_path)["assets"]
        if a.get("designObject", {}).get("id") == "building:pod"
    )


def test_current_mother_cannot_be_deleted_while_draft_layout_references_it(tmp_path):
    from fastapi import HTTPException

    from devtools.asset_design.design import assert_not_adopted

    prepare(tmp_path)
    publish_object(tmp_path, "layout:pod")
    catalog = read_catalog(tmp_path)
    mother = next(
        a
        for a in catalog["assets"]
        if a.get("designObject", {}).get("id") == "part:common_chair"
    )
    with pytest.raises(HTTPException) as error:
        assert_not_adopted(tmp_path, mother["id"])
    assert error.value.status_code == 409
