"""The building preview exposes the authored components and wall placement."""

import json
import struct
from pathlib import Path

from test.godot.asset_geometry import read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"


def test_stair_wall_uses_one_texture_tile():
    doc, binary = read_glb(NEST / "buildings/main/central-building.glb")
    wall = next(
        node
        for node in doc["nodes"]
        if node.get("extras", {}).get("source_name")
        == "L1 inner sofa background plaster face"
    )
    primitive = doc["meshes"][wall["mesh"]]["primitives"][0]
    uv = doc["accessors"][primitive["attributes"]["TEXCOORD_0"]]
    view = doc["bufferViews"][uv["bufferView"]]
    start = view.get("byteOffset", 0) + uv.get("byteOffset", 0)
    stride = view.get("byteStride", 8)
    coords = [
        struct.unpack_from("<2f", binary, start + i * stride)
        for i in range(uv["count"])
    ]
    assert all(0 < u < 1 and 0 < v < 1 for u, v in coords)
    assert max(u for u, _ in coords) - min(u for u, _ in coords) > 0.9
    assert max(v for _, v in coords) - min(v for _, v in coords) > 0.9


def test_building_menu_names_bedroom_structure_and_exposes_eight_sliding_doors():
    graph = json.loads((NEST / "assembly/asset-index.json").read_text())["fileGraph"]
    entries = graph["entries"]
    bedroom = entries["source:pod-building"]
    assert bedroom["title"] == "共享小屋"
    main = entries["source:central-building"]
    doors = next(
        part for part in main["components"] if part["id"] == "bedroom-sliding-door"
    )
    assert doors["count"] == 8
    placements = json.loads((NEST / "assembly/runtime-bindings.json").read_text())[
        "placements"
    ]
    assert set(doors["paths"]) == {
        path for path, extras in placements.items() if extras.get("door_prototype")
    }
