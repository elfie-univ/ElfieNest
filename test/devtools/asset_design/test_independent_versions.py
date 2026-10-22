"""An export carrying unchanged scenery must not mint object revisions."""

import json
import struct
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.reindex import reconcile
from test.devtools.asset_design.test_design import confirm, model, open_scene, setup


def objects(client):
    return {
        o["id"]: o for o in client.get("/assets/design/design/index").json()["objects"]
    }


def test_pod_edit_does_not_create_central_or_layout_revision(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        index = objects(client)
        central = index["building:central"]["versions"]
        assert len(central) == 1
        assert {s["asset"] for s in central[0]["sources"]} == {"v1", "v2"}
        assert len(index["building:pod"]["versions"]) == 2
        assert len(index["layout:pod"]["versions"]) == 1
        assert central[0]["title"].startswith("主楼")


def test_prepending_a_carried_export_does_not_reorder_object_history(tmp_path):
    assets = setup(tmp_path)
    copy = model(tmp_path, "new_copy", 1)
    (tmp_path / "catalog.json").write_text(json.dumps({"assets": [copy, *assets]}))
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        index = objects(client)
        assert index["building:central"]["versions"][0]["asset"] == "v1"
        assert [v["asset"] for v in index["building:pod"]["versions"]] == ["v2", "v1"]


def test_all_floor_composition_keeps_unchanged_floors(tmp_path):
    assets = setup(tmp_path)
    for index, asset in enumerate(assets):
        path = tmp_path / asset["primaryModel"]
        doc = json.loads(path.read_bytes()[20:])
        doc["nodes"][3]["translation"] = [index, 0, 0]
        doc["nodes"].append(
            {"mesh": 0, "extras": {"module": "central", "floor": 1, "furniture": True}}
        )
        doc["scenes"][0]["nodes"].append(6)
        data = json.dumps(doc).encode()
        data += b" " * (-len(data) % 4)
        path.write_bytes(
            struct.pack("<5I", 0x46546C67, 2, 20 + len(data), len(data), 0x4E4F534A)
            + data
        )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert len(objects(client)["layout:central:1"]["versions"]) == 1
        scene = open_scene(client, "layout:central", "v2")
        assert scene["layers"][0]["nodes"] == [3, 6]
        assert not scene["confirmable"]


def test_confirmed_object_survives_unrelated_change_in_same_file(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        scene = open_scene(client, "building:central", "v1")
        assert confirm(client, scene).status_code == 200
        model(tmp_path, "v1", 42)  # Only the small house moves.
        overview = open_scene(client, "overview")
        assert any(
            layer["object"] == "building:central" for layer in overview["layers"]
        )
        assert not any(i["object"] == "building:central" for i in overview["issues"])


def test_real_object_change_invalidates_confirmation(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        model(tmp_path, "v1", 42)
        overview = open_scene(client, "overview")
        assert not any(
            layer["object"] == "building:pod" for layer in overview["layers"]
        )


def test_reference_confirmation_is_separate_from_object_adoption(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        scene = open_scene(client, "layout:pod", "v1")
        assert confirm(client, scene).status_code == 200
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        assert objects(client)["layout:pod"]["current"]["contentDigest"]
        assert open_scene(client, "layout:pod", "v1")["adopted"] is True


def test_mesh_bytes_and_material_changes_are_object_changes(tmp_path):
    def save(name, position, color):
        asset = model(tmp_path, name)
        path = tmp_path / asset["primaryModel"]
        raw = path.read_bytes()
        doc = json.loads(raw[20:])
        doc.update(
            meshes=[{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
            accessors=[
                {"bufferView": 0, "componentType": 5126, "count": 1, "type": "VEC3"}
            ],
            bufferViews=[{"buffer": 0, "byteLength": 12}],
            buffers=[{"byteLength": 12}],
            materials=[{"pbrMetallicRoughness": {"baseColorFactor": color}}],
        )
        data = json.dumps(doc).encode()
        data += b" " * (-len(data) % 4)
        path.write_bytes(
            struct.pack("<5I", 0x46546C67, 2, 40 + len(data), len(data), 0x4E4F534A)
            + data
            + struct.pack("<2I3f", 12, 0x004E4942, position, 0, 0)
        )
        return asset

    assets = [
        save("v1", 0, [1, 1, 1, 1]),
        save("copy", 0, [1, 1, 1, 1]),
        save("geometry", 2, [1, 1, 1, 1]),
        save("material", 2, [0, 1, 1, 1]),
    ]
    (tmp_path / "catalog.json").write_text(json.dumps({"assets": assets}))
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert len(objects(client)["building:central"]["versions"]) == 3


def test_reconcile_preserves_confirmed_sources_and_original_history(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "building:pod", "v2")).status_code == 200
        )
    path = tmp_path / "adoptions.json"
    old = json.loads(path.read_text())
    old["current"]["building:pod"].pop("contentDigest")
    path.write_text(json.dumps(old))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    reconcile(tmp_path)
    assert path.read_bytes() == before[path.name]
    report = reconcile(tmp_path, apply=True)
    new = json.loads(path.read_text())
    assert new["history"] == old["history"]
    assert new["current"]["building:pod"]["version"] == "v2"
    assert (
        new["current"]["building:pod"]["digest"]
        == old["current"]["building:pod"]["digest"]
    )
    assert new["current"]["building:pod"]["contentDigest"]
    assert Path(report["confirmationBackup"]).read_bytes() == before[path.name]
    for name, contents in before.items():
        if name != path.name:
            assert (tmp_path / name).read_bytes() == contents


def test_reconcile_refuses_changed_legacy_confirmation(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "building:pod", "v2")).status_code == 200
        )
    path = tmp_path / "adoptions.json"
    state = json.loads(path.read_text())
    state["current"]["building:pod"].pop("contentDigest")
    path.write_text(json.dumps(state))
    before = path.read_bytes()
    model(tmp_path, "v2", 45)
    with pytest.raises(ValueError, match="source changed"):
        reconcile(tmp_path, apply=True)
    assert path.read_bytes() == before


def test_historical_and_overview_content_can_be_compared_without_removing_sources(
    tmp_path,
):
    assets = setup(tmp_path)
    duplicate = model(tmp_path, "copy")
    historical = model(tmp_path, "historical")
    historical["category"] = "pod"
    (tmp_path / "catalog.json").write_text(
        json.dumps({"assets": [*assets, duplicate, historical]})
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        index = objects(client)
        versions = {v["id"]: v for v in index["overview"]["versions"]}
        assert versions["v1"]["contentDigest"] == versions["copy"]["contentDigest"]
        assert versions["v1"]["contentDigest"] != versions["v2"]["contentDigest"]
        assert index["saved:historical"]["versions"][0]["contentDigest"]
        assert len(versions) == 3
        assert (tmp_path / "copy.glb").exists()
