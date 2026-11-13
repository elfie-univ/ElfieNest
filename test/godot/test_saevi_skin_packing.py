"""Exact pre-packing skin semantics and immutable source payload regression."""

import hashlib

from test.godot.test_saevi_seated_tail_asset import accessor, read_asset, skin_rows


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
                assert spec["count"] == doc["accessors"][attrs["POSITION"]]["count"]


def test_packed_accessors_keep_all_geometry_and_morph_rows():
    doc, binary = read_asset()
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            count = doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
            for attributes in [primitive["attributes"], *primitive.get("targets", [])]:
                assert all(
                    len(accessor(doc, binary, index)) == count
                    for index in attributes.values()
                )
            indices = accessor(doc, binary, primitive["indices"])
            assert len(indices) % 3 == 0
            assert max(index for (index,) in indices) < count
