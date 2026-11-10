"""Exact pre-packing skin semantics and immutable source payload regression."""

import copy
import hashlib
import json

from test.godot.test_saevi_seated_tail_asset import read_asset, skin_rows


def test_all_vertex_influences_preserved():
    doc, binary = read_asset()
    joints, weights = skin_rows(doc, binary)
    skin = doc["skins"][0]
    rows = [
        sorted(
            (doc["nodes"][skin["joints"][j]]["name"], w)
            for j, w in zip(js, ws)
            if w != 0
        )
        for js, ws in zip(joints, weights)
    ]
    assert len(rows) == 115340
    assert max(map(len, rows)) == 4
    assert hashlib.sha256(repr(rows).encode()).hexdigest() == (
        "114f64e4a9edaeafaa9219e6fa2c5156dbd57855925f82ae7689b71ad0bf9551"
    )
    frozen = dict(doc)
    for key in ("buffers", "accessors", "bufferViews", "meshes"):
        frozen.pop(key)
    assert hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest() == (
        "4844cc5ede2c5168a4d611dab45ab3645cac503c3bffd7c33896997772f19351"
    )
    # Preserve the complete pre-packing binary, including historical accessors.
    assert hashlib.sha256(binary[:15721552]).hexdigest() == (
        "02ff3dd8482007029394b3f5d59dbf32f2d191f7811aa4f40af06a01a87856e4"
    )


def test_only_four_skin_slots_are_exposed():
    doc, _ = read_asset()
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            attrs = primitive["attributes"]
            assert {k for k in attrs if k.startswith(("JOINTS_", "WEIGHTS_"))} == {
                "JOINTS_0",
                "WEIGHTS_0",
            }
            for name in ("JOINTS_0", "WEIGHTS_0"):
                spec = doc["accessors"][attrs[name]]
                assert spec["type"] == "VEC4"
                assert spec["count"] == 115340


def test_original_accessor_tables_and_geometry_references_preserved():
    doc, _ = read_asset()
    meshes = copy.deepcopy(doc["meshes"])
    for mesh in meshes:
        for primitive in mesh["primitives"]:
            primitive["attributes"] = {
                key: value
                for key, value in primitive["attributes"].items()
                if not key.startswith(("JOINTS_", "WEIGHTS_"))
            }
    frozen = [doc["accessors"][:11], doc["bufferViews"][:12], meshes]
    assert hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest() == (
        "a7d5163b4051f079297ffbda9e3d6b482ac3a8c463bd93f398873f8675ed3f26"
    )
