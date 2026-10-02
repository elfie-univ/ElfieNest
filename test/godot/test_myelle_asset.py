"""Validate Myelle's exported skin and shared animation package."""

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "godot_project" / "characters" / "cat"


def test_myelle_glb_has_a_skinned_mesh_and_connected_tail_chain() -> None:
    payload = (PACKAGE / "cat.glb").read_bytes()
    magic, version, length = struct.unpack_from("<III", payload)
    assert (magic, version, length) == (0x46546C67, 2, len(payload))
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    assert chunk_type == 0x4E4F534A
    document = json.loads(payload[20 : 20 + chunk_length])
    nodes = document["nodes"]
    names = {node.get("name"): index for index, node in enumerate(nodes)}
    assert any("mesh" in node and "skin" in node for node in nodes)
    for parent, child in zip(
        ("mixamorig:Hips", "Tail_01", "Tail_02", "Tail_03"),
        ("Tail_01", "Tail_02", "Tail_03", "Tail_04"),
    ):
        assert names[child] in nodes[names[parent]]["children"]
    assert not document.get("animations")
    assert document["images"]
    assert all("bufferView" in image for image in document["images"])

    binary_start = 20 + chunk_length + 8
    binary = payload[binary_start:]
    primitive = document["meshes"][0]["primitives"][0]
    joints = _accessor(document, binary, primitive["attributes"]["JOINTS_0"])
    weights = _accessor(document, binary, primitive["attributes"]["WEIGHTS_0"])
    skin = document["skins"][0]
    joint_names = [nodes[index]["name"] for index in skin["joints"]]
    tail_vertices = 0
    for indices, influences in zip(joints, weights):
        active = {
            joint_names[index]
            for index, weight in zip(indices, influences)
            if weight > 0.00001
        }
        assert abs(sum(influences) - 1) < 0.0001
        if active.intersection({"Tail_01", "Tail_02", "Tail_03", "Tail_04"}):
            tail_vertices += 1
            assert active <= {
                "mixamorig:Hips",
                "Tail_01",
                "Tail_02",
                "Tail_03",
                "Tail_04",
            }
    assert tail_vertices > 1000


def _accessor(document: dict, binary: bytes, index: int) -> list[tuple]:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    formats = {5121: "B", 5123: "H", 5126: "f"}
    value_format = "<" + formats[accessor["componentType"]] * 4
    stride = view.get("byteStride", struct.calcsize(value_format))
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [
        struct.unpack_from(value_format, binary, offset + item * stride)
        for item in range(accessor["count"])
    ]


def test_myelle_manifest_binds_its_own_tail_and_shared_actions() -> None:
    manifest = json.loads((PACKAGE / "species_manifest.json").read_text())
    assert manifest["species_id"] == "cat"
    assert manifest["appearance_bindings"]["bone_scales"]["TailLength"]["bones"] == [
        "Tail_01",
        "Tail_02",
        "Tail_03",
        "Tail_04",
    ]
    assert {"idle", "walking", "running", "jump"} <= set(
        manifest["required_animations"]
    )
    for path in manifest["shared_animation_files"].values():
        assert (ROOT / "godot_project" / path.removeprefix("res://")).is_file()
