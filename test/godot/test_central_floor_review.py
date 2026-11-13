"""Check the rug assets and the floor-level wall-niche references."""

import json
import struct
from pathlib import Path

import pytest

from test.godot.asset_geometry import read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"
RUGS = (
    ("main-floor-2/central-games-central-local.glb", "games_central_rug"),
    ("main-floor-2/central-games-chess-local.glb", "games_left_chess_rug"),
    ("main-floor-2/central-games-console.glb", "games_right_console_rug"),
    ("main-floor-3/central-quiet-daybed-local.glb", "quiet_front_daybed_rug"),
)


def accessor(document, binary, index):
    field = document["accessors"][index]
    view = document["bufferViews"][field["bufferView"]]
    component = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[field["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[field["type"]]
    record = struct.Struct("<" + component * width)
    start = view.get("byteOffset", 0) + field.get("byteOffset", 0)
    stride = view.get("byteStride", record.size)
    return [
        record.unpack_from(binary, start + i * stride) for i in range(field["count"])
    ]


@pytest.mark.parametrize("file,name", RUGS)
def test_rug_cap_has_upward_normals_separate_from_the_rounded_rim(file, name):
    document, binary = read_glb(NEST / "furniture/sets" / file)
    (node,) = [
        n
        for n in document["nodes"]
        if n.get("extras", {}).get("v044_path", "").endswith("/" + name)
    ]
    surface = document["meshes"][node["mesh"]]["primitives"][0]
    attrs = surface["attributes"]
    positions = accessor(document, binary, attrs["POSITION"])
    normals = accessor(document, binary, attrs["NORMAL"])
    tangents = accessor(document, binary, attrs["TANGENT"])
    indices = [i for (i,) in accessor(document, binary, surface["indices"])]
    peak = max(position[1] for position in positions)
    cap, rim = set(), set()
    for start in range(0, len(indices), 3):
        corners = indices[start : start + 3]
        target = (
            cap if all(abs(positions[i][1] - peak) < 0.00002 for i in corners) else rim
        )
        target.update(corners)

    assert cap and rim and not cap & rim
    assert all(normals[i] == (0.0, 1.0, 0.0) for i in cap)
    assert all(tangents[i][1] == 0.0 and abs(tangents[i][3]) == 1.0 for i in cap)
    assert any(0.1 < abs(normals[i][1]) < 0.95 for i in rim)


def test_bedroom_rug_uses_matte_braid_on_the_rounded_base():
    document, _ = read_glb(NEST / "furniture/shared/bedroom/bedroom-rug.glb")
    (mesh,) = document["meshes"]
    (surface,) = mesh["primitives"]
    assert document["accessors"][surface["indices"]]["count"] == 764 * 3

    material = document["materials"][surface["material"]]
    finish = material["pbrMetallicRoughness"]
    assert finish["metallicFactor"] == 0 and finish["roughnessFactor"] >= 0.9
    assert not material.get("emissiveTexture") and not any(
        material.get("emissiveFactor", [])
    )
    assert material["normalTexture"]["scale"] == pytest.approx(0.2)
    texture = document["textures"][finish["baseColorTexture"]["index"]]
    assert document["samplers"][texture["sampler"]]["minFilter"] == 9987
    image = document["images"][texture["source"]]
    assert image["uri"] == "../../textures/bedroom-rug-braid.png"
    assert (NEST / "furniture/textures/bedroom-rug-braid.png").is_file()


@pytest.mark.parametrize("floor,count", [(1, 35), (2, 9)])
def test_wall_niche_furniture_is_reached_through_a_floor_zone(floor, count):
    entries = json.loads((NEST / "assembly/asset-index.json").read_text())["fileGraph"][
        "entries"
    ]
    layout = entries[f"view:central-layout-{floor}"]
    zone_id = f"view:central-niche-{floor}"
    (link,) = [row for row in layout["parts"] if row["id"] == zone_id]
    zone = entries[zone_id]
    assert zone["file"].endswith(f"/central-niche-{floor}.scn")
    detail_paths = {path for row in zone["parts"] for path in row["paths"]}
    assert set(link["paths"]) == detail_paths and len(detail_paths) == count
    assert all(
        not (detail_paths & set(row.get("paths", [])))
        for row in layout["parts"]
        if row["id"] != zone_id
    )
