"""Bedroom wood textures must reference real, noncollapsed UV coordinates."""

import math
import struct

import pytest

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import ROOT


def _check_desktops(model, expected_count):
    count = 0
    for node in model.doc["nodes"]:
        if node.get("extras", {}).get("piece") != "worktop":
            continue
        count += 1
        for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
            material = model.doc["materials"][primitive["material"]]
            texture = material["pbrMetallicRoughness"]["baseColorTexture"]
            channel = texture.get("texCoord", 0)
            assert channel >= 0, "Texture coordinate channels cannot be negative"
            uv = model.doc["accessors"][primitive["attributes"][f"TEXCOORD_{channel}"]]
            position = model.doc["accessors"][primitive["attributes"]["POSITION"]]
            assert uv["count"] == position["count"]
            assert uv["type"] == "VEC2" and uv["componentType"] == 5126
            view = model.doc["bufferViews"][uv["bufferView"]]
            data = model.view(uv["bufferView"])
            values = [
                struct.unpack_from(
                    "<ff", data, uv.get("byteOffset", 0) + i * view.get("byteStride", 8)
                )
                for i in range(uv["count"])
            ]
            assert all(math.isfinite(value) for pair in values for value in pair)
            assert all(
                max(pair[axis] for pair in values) - min(pair[axis] for pair in values)
                > 0.1
                for axis in (0, 1)
            )
    assert count == expected_count


@pytest.mark.parametrize(
    "relative,count",
    [
        ("godot_project/rooms/estate/ElfieNest-complete-final.glb", 32),
    ],
)
def test_bedroom_desktop_has_valid_texture_coordinates(relative, count):
    _check_desktops(_Model(str(ROOT / relative)), count)
