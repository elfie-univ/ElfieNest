"""Object adoption is scoped, persistent, conflict-safe and never rewrites models."""

import json
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from devtools.asset_design.app import create_app
from devtools.asset_design.catalog_store import read_catalog, save_catalog


def model(root, asset_id, offset=0, layout_offset=0):
    nodes = [
        {"name": "wall", "mesh": 0, "extras": {"module": "M01", "floor": 1}},
        {
            "name": "bed",
            "mesh": 0,
            "extras": {"module": "M01", "floor": 1, "furniture": True},
        },
        {"name": "wall", "mesh": 0, "extras": {"module": "central", "floor": 1}},
        {
            "name": "table",
            "mesh": 0,
            "extras": {"module": "central", "floor": 2, "furniture": True},
        },
        {"name": "ruler", "mesh": 0, "extras": {"module": "M01", "reference": True}},
        {"name": "garden", "mesh": 0, "extras": {"design_role": "landscape"}},
    ]
    nodes[0]["translation"] = [offset, 0, 0]
    nodes[1]["translation"] = [layout_offset, 0, 0]
    data = json.dumps(
        {
            "asset": {"version": "2.0"},
            "scene": 0,
            "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes,
            "meshes": [{"primitives": [{"attributes": {}}]}],
        }
    ).encode()
    data += b" " * (-len(data) % 4)
    path = root / (asset_id + ".glb")
    path.write_bytes(
        struct.pack("<4sIIII", b"glTF", 2, 20 + len(data), len(data), 0x4E4F534A) + data
    )
    return {
        "id": asset_id,
        "title": asset_id,
        "category": "estate",
        "primaryModel": path.name,
        "models": [path.name],
        "files": [
            {
                "path": path.name,
                "name": path.name,
                "kind": "model",
                "bytes": path.stat().st_size,
            }
        ],
    }


def setup(root):
    assets = [model(root, "v1"), model(root, "v2", 1)]
    (root / "catalog.json").write_text(json.dumps({"assets": assets}))
    return assets


def open_scene(client, obj, version=None):
    response = client.get(
        "/assets/design/design/scene",
        params={"object": obj, **({"version": version} if version else {})},
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, scene):
    return client.post(
        "/assets/design/design/confirm",
        json={"sceneId": scene["id"], "expectedCurrent": scene["expectedCurrent"]},
    )


def test_inventory_separates_buildings_layouts_landscape_and_keeps_all_versions(
    tmp_path,
):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.get("/assets/design/design/index")
        assert response.status_code == 200, response.text
        objects = {o["id"]: o for o in response.json()["objects"]}
        assert objects["building:pod"]["group"] == "building"
        assert objects["layout:pod"]["group"] == "layout"
        assert objects["landscape:site"]["group"] == "landscape"
        assert len(objects["building:pod"]["versions"]) == 2
        assert open_scene(client, "building:pod", "v2")["layers"][0]["nodes"] == [0]
        assert open_scene(client, "layout:pod", "v1")["layers"][0]["nodes"] == [1]
        assert open_scene(client, "overview")["layers"] == []
        assert (
            client.get("/assets/design/catalog.json").json()["assets"][0]["id"] == "v1"
        )


def test_confirm_older_version_updates_only_one_object_and_survives_restart(tmp_path):
    setup(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "building:pod", "v2")).status_code == 200
        )
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        total = open_scene(client, "overview")
        assert [(x["object"], x["version"]) for x in total["layers"]] == [
            ("building:pod", "v1")
        ]
        assert any(x["object"] == "building:central" for x in total["issues"])
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert open_scene(client, "overview")["layers"][0]["version"] == "v1"
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content


def test_building_reference_requires_confirmed_version(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        preview = open_scene(client, "layout:pod", "v1")
        assert not any(x["reference"] for x in preview["layers"])
        assert open_scene(client, "overview")["layers"] == []
        assert confirm(client, preview).status_code == 200
        assert (
            "building:pod"
            not in json.loads((tmp_path / "adoptions.json").read_text())["current"]
        )
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        preview = open_scene(client, "layout:pod", "v2")
        reference = next(x for x in preview["layers"] if x["reference"])
        assert reference["version"] == "v1"
        assert not reference.get("unconfirmed")
        model(tmp_path, "v1", 99)
        assert not any(
            x["reference"] for x in open_scene(client, "layout:pod", "v2")["layers"]
        )


def test_references_pin_confirmed_matching_layout_and_do_not_adopt_it(tmp_path):
    setup(tmp_path)
    model(tmp_path, "v2", 1, layout_offset=1)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "layout:pod", "v1")).status_code == 200
        )
        building = open_scene(client, "building:pod", "v2")
        assert [
            (x["object"], x["version"]) for x in building["layers"] if x["reference"]
        ] == [("layout:pod", "v1")]
        assert (
            confirm(client, open_scene(client, "layout:pod", "v2")).status_code == 200
        )
        assert confirm(client, building).status_code == 200
        total = open_scene(client, "overview")
        assert (
            next(x for x in total["layers"] if x["object"] == "layout:pod")["version"]
            == "v2"
        )
        assert total["issues"]  # The newly combined geometry still needs review.


def test_stale_same_object_conflict_but_parallel_different_objects_merge(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        a = open_scene(client, "building:pod", "v1")
        b = open_scene(client, "building:pod", "v2")
        assert confirm(client, a).status_code == 200
        assert confirm(client, b).status_code == 409
        scenes = [
            open_scene(client, "building:central", "v1"),
            open_scene(client, "layout:pod", "v2"),
        ]
        with ThreadPoolExecutor(2) as pool:
            assert list(pool.map(lambda s: confirm(client, s).status_code, scenes)) == [
                200,
                200,
            ]
        assert len(open_scene(client, "overview")["layers"]) == 3


def test_rejects_cross_origin_tampering_and_changed_source_without_writes(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        scene = open_scene(client, "building:pod", "v1")
        body = {"sceneId": scene["id"], "expectedCurrent": None}
        assert (
            client.post(
                "/assets/design/design/confirm",
                json=body,
                headers={"origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/assets/design/design/confirm", json={**body, "sceneId": "unknown"}
            ).status_code
            == 409
        )
        model(tmp_path, "v1", 99)
        assert confirm(client, scene).status_code == 409
        assert open_scene(client, "overview")["layers"] == []


def test_adopted_or_pinned_assets_cannot_be_deleted(tmp_path):
    setup(tmp_path)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert (
            confirm(client, open_scene(client, "building:pod", "v1")).status_code == 200
        )
        response = client.delete("/assets/cleanup/assets/v1")
        assert response.status_code == 409
        assert (tmp_path / "v1.glb").is_file()


def test_repeated_houses_share_one_design_and_one_adoption(tmp_path):
    assets = setup(tmp_path)
    source = tmp_path / assets[0]["primaryModel"]
    raw = source.read_bytes()
    doc = json.loads(raw[20:])
    doc["nodes"].append(
        {
            "name": "wall",
            "mesh": 0,
            "translation": [12, 0, 0],
            "extras": {"module": "M02", "floor": 1},
        }
    )
    doc["nodes"].append(
        {
            "name": "bed",
            "mesh": 0,
            "translation": [12, 0, 0],
            "extras": {"module": "M02", "floor": 1, "furniture": True},
        }
    )
    doc["scenes"][0]["nodes"].extend([6, 7])
    data = json.dumps(doc).encode()
    data += b" " * (-len(data) % 4)
    source.write_bytes(
        struct.pack("<4sIIII", b"glTF", 2, 20 + len(data), len(data), 0x4E4F534A) + data
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        objects = client.get("/assets/design/design/index").json()["objects"]
        houses = [
            o for o in objects if o["group"] == "building" and o["module"] != "central"
        ]
        assert [o["id"] for o in houses] == ["building:pod"]
        assert not any(o["id"].startswith("layout:M") for o in objects)
        scene = open_scene(client, "building:pod", "v1")
        assert scene["layers"][0]["nodes"] == [0]
        assert confirm(client, scene).status_code == 200
        total = open_scene(client, "overview")
        assert len(total["layers"]) == 1
        assert total["layers"][0]["placements"] == {"M01": 0, "M02": 6}


def test_design_frontend_selection_and_template_transforms():
    subprocess.run(
        ["node", "--test", str(Path(__file__).with_name("design-state.test.mjs"))],
        check=True,
    )


def test_floor_and_terrace_scopes_keep_independent_confirmations(tmp_path):
    assets = setup(tmp_path)
    path = tmp_path / assets[0]["primaryModel"]
    doc = json.loads(path.read_bytes()[20:])
    doc["nodes"].extend(
        [
            {"name": "wall", "mesh": 0, "extras": {"module": "M02", "floor": 1}},
            {
                "name": "reading",
                "mesh": 0,
                "extras": {"module": "M01", "floor": 2, "furniture": True},
            },
            {
                "name": "painting",
                "mesh": 0,
                "extras": {"module": "M02", "floor": 2, "furniture": True},
            },
            {
                "name": "sofa",
                "mesh": 0,
                "extras": {"module": "central", "floor": 1, "furniture": True},
            },
        ]
    )
    doc["scenes"][0]["nodes"] = list(range(len(doc["nodes"])))
    data = json.dumps(doc).encode()
    data += b" " * (-len(data) % 4)
    path.write_bytes(
        struct.pack("<4sIIII", b"glTF", 2, 20 + len(data), len(data), 0x4E4F534A) + data
    )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        objects = client.get("/assets/design/design/index").json()["objects"]
        by_id = {obj["id"]: obj for obj in objects}
        assert by_id["layout:central:2"]["collection"] == "layout:central"
        assert by_id["layout:terrace:M02"]["collection"] == "layout:terraces"
        assert open_scene(client, "layout:pod", "v1")["layers"][0]["nodes"] == [1]
        assert open_scene(client, "layout:terrace:M01", "v1")["layers"][0]["nodes"] == [
            7
        ]
        terrace = open_scene(client, "layout:terrace:M02", "v1")
        assert terrace["layers"][0]["nodes"] == [8]
        assert terrace["review"]["axis"] == "module"
        assert not open_scene(client, "layout:terraces", "v1")["confirmable"]
        assert confirm(client, terrace).status_code == 200
        assert (
            confirm(client, open_scene(client, "layout:central:2", "v1")).status_code
            == 200
        )
        assert not open_scene(client, "layout:central", "v1")["confirmable"]
        assert {
            layer["object"] for layer in open_scene(client, "overview")["layers"]
        } == {"layout:terrace:M02", "layout:central:2"}


def test_local_historical_versions_remain_in_their_content_collections(tmp_path):
    assets = setup(tmp_path)
    assets[0]["category"] = "pod"
    (tmp_path / "catalog.json").write_text(json.dumps({"assets": assets}))
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        index = client.get("/assets/design/design/index").json()
        assert "archive" not in index["groups"]
        saved = next(obj for obj in index["objects"] if obj.get("historical"))
        assert saved["collection"] == "building:pod"
        assert saved["versions"][0]["id"] == "v1"
        scene = open_scene(client, saved["id"], "v1")
        assert not scene["confirmable"]
        assert len(scene["layers"][0]["nodes"]) == 6
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content


def test_source_only_history_remains_selectable_and_downloadable(tmp_path):
    setup(tmp_path)
    source = tmp_path / "old" / "room.blend"
    source.parent.mkdir()
    source.write_bytes(b"old source")
    catalog_path = tmp_path / "catalog.json"
    catalog = read_catalog(catalog_path.parent)
    catalog["assets"].append(
        {
            "id": "old-room",
            "title": "旧小屋源文件",
            "category": "pod",
            "files": [
                {
                    "path": "old/room.blend",
                    "name": "room.blend",
                    "kind": "source",
                    "bytes": 10,
                }
            ],
        }
    )
    save_catalog(catalog_path.parent, catalog)
    before = catalog_path.read_bytes()
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        objects = client.get("/assets/design/design/index").json()["objects"]
        saved = next(obj for obj in objects if obj["id"] == "saved:old-room")
        assert saved["collection"] == "building:pod"
        assert saved["historical"]
        assert saved["versions"][0]["sourceOnly"]
        assert saved["versions"][0]["file"] is None
        assert (
            client.get("/assets/design/files/old/room.blend?download=1").content
            == b"old source"
        )
    assert catalog_path.read_bytes() == before
