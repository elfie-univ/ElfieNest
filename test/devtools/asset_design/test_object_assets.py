"""Physical object sources, publishing and confirmation survive legacy archival."""

import json

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.object_assets import publish_object, split_assets
from test.devtools.asset_design.test_design import confirm, open_scene, setup


def test_split_preserves_confirmation_and_isolates_builds(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        confirm(client, open_scene(client, "building:pod", "v2"))
        before = json.loads((tmp_path / "adoptions.json").read_text())
        original = (tmp_path / "v2.glb").read_bytes()
        report = split_assets(tmp_path)
        after = json.loads((tmp_path / "adoptions.json").read_text())
        assert after["history"] == before["history"]
        assert (
            after["current"]["building:pod"]["contentDigest"]
            == before["current"]["building:pod"]["contentDigest"]
        )
        assert (tmp_path / "v2.glb").read_bytes() == original
        scene = open_scene(client, "building:pod", "v2")
        assert scene["adopted"]
        assert scene["layers"][0]["file"] != "v2.glb"
        assert report["verified_versions"] > 0
        # The source is self-contained; legacy input files are unnecessary for publishing.
        (tmp_path / "v1.glb").unlink()
        (tmp_path / "v2.glb").unlink()
        catalog_before = json.loads((tmp_path / "catalog.json").read_text())
        assert publish_object(tmp_path, "building:pod")["changed"] is False
        assert json.loads((tmp_path / "catalog.json").read_text()) == catalog_before
        assert open_scene(client, "building:pod", "v2")["adopted"]
        index = client.get("/assets/design/design/index").json()
        pod = next(o for o in index["objects"] if o["id"] == "building:pod")
        assert len(pod["versions"]) == 1
        assert pod["versions"][0]["title"].endswith("V002")


def test_publishing_furniture_changes_only_its_versions_and_does_not_confirm(tmp_path):
    import struct

    setup(tmp_path)
    split_assets(tmp_path)
    before = json.loads((tmp_path / "catalog.json").read_text())
    source = tmp_path / "layouts/pod_bedroom/source/model.glb"
    raw = source.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20 : 20 + length])
    bed = next(
        n for n in doc["nodes"] if "mesh" in n and n.get("extras", {}).get("furniture")
    )
    bed["translation"] = [3, 0, 0]
    data = json.dumps(doc).encode()
    data += b" " * (-len(data) % 4)
    source.write_bytes(
        struct.pack("<5I", 0x46546C67, 2, 20 + len(data), len(data), 0x4E4F534A) + data
    )
    result = publish_object(tmp_path, "layout:pod")
    assert result["changed"]
    after = json.loads((tmp_path / "catalog.json").read_text())
    assert after["assets"][:-1] == before["assets"]
    assert after["assets"][-1]["designObject"]["id"] == "layout:pod"
    assert not (tmp_path / "adoptions.json").exists()
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        scene = open_scene(client, "layout:pod")
        assert scene["confirmable"] and not scene["adopted"]
        confirm(client, scene)
        current = json.loads((tmp_path / "adoptions.json").read_text())["current"]
        assert list(current) == ["layout:pod"]
        aggregate = open_scene(client, "layout:central")
        assert not aggregate["confirmable"]
        assert all(layer["object"] != "layout:central" for layer in aggregate["layers"])


def test_archived_revision_restores_without_changing_adoption_and_confirmed_file_is_protected(
    tmp_path,
):
    import pytest
    from fastapi import HTTPException

    from devtools.asset_design.design import assert_not_adopted
    from devtools.asset_design.object_assets import restore_version

    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        confirm(client, open_scene(client, "building:pod", "v2"))
        split_assets(tmp_path)
        state = (tmp_path / "adoptions.json").read_bytes()
        with pytest.raises(HTTPException):
            assert_not_adopted(tmp_path, "building_pod_v002")
        assert (tmp_path / "buildings/pod/versions/v001/model.glb.gz").is_file()
        assert not (tmp_path / "buildings/pod/versions/v001/model.glb").exists()
        restore_version(tmp_path, "building:pod", 1)
        assert (tmp_path / "adoptions.json").read_bytes() == state
        index = client.get("/assets/design/design/index").json()
        assert (
            len(
                next(o for o in index["objects"] if o["id"] == "building:pod")[
                    "versions"
                ]
            )
            == 2
        )


def test_furniture_source_rejects_building_geometry(tmp_path):
    import pytest

    setup(tmp_path)
    split_assets(tmp_path)
    source = tmp_path / "layouts/pod_bedroom/source/model.glb"
    source.write_bytes((tmp_path / "buildings/pod/source/model.glb").read_bytes())
    catalog = (tmp_path / "catalog.json").read_bytes()
    with pytest.raises(ValueError, match="Architecture"):
        publish_object(tmp_path, "layout:pod")
    assert (tmp_path / "catalog.json").read_bytes() == catalog


def test_extraction_retains_material_extension_declarations(tmp_path):
    import struct

    from devtools.asset_design.object_glb import extract_glb

    setup(tmp_path)
    path = tmp_path / "v1.glb"
    doc = json.loads(path.read_bytes()[20:])
    doc["extensionsUsed"] = ["KHR_materials_transmission"]
    doc["materials"] = [
        {"extensions": {"KHR_materials_transmission": {"transmissionFactor": 1}}}
    ]
    doc["meshes"][0]["primitives"][0]["material"] = 0
    data = json.dumps(doc).encode()
    data += b" " * (-len(data) % 4)
    path.write_bytes(
        struct.pack("<5I", 0x46546C67, 2, 20 + len(data), len(data), 0x4E4F534A) + data
    )
    extracted, _ = extract_glb(path, [0])
    result = json.loads(extracted[20:])
    assert result["extensionsUsed"] == doc["extensionsUsed"]
    assert result["materials"] == doc["materials"]
    assert sum("mesh" in n for n in result["nodes"]) == 1
