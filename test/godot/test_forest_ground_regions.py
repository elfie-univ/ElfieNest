"""Requested forest junctions and shared landscape-stone ownership."""

import json
from functools import lru_cache
from pathlib import Path

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import _values

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"


@lru_cache
def ground():
    return _Model(str(NEST / "courtyard/parts/ground/shared-ground.glb"))


def terrain_samples(x, z):
    source = ground()
    nodes = [
        node
        for node in source.doc["nodes"]
        if node.get("extras", {})
        .get("source_name", "")
        .startswith("COMPLETE Building garden island")
    ]
    result = []
    for primitive in (
        p for node in nodes for p in source.doc["meshes"][node["mesh"]]["primitives"]
    ):
        points = _values(source, primitive["attributes"]["POSITION"])
        indices = [row[0] for row in _values(source, primitive["indices"])]
        for at in range(0, len(indices), 3):
            a, b, c = [points[i] for i in indices[at : at + 3]]
            denominator = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(denominator) < 1e-10:
                continue
            u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / denominator
            v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / denominator
            if min(u, v, 1 - u - v) >= -1e-6:
                y = u * a[1] + v * b[1] + (1 - u - v) * c[1]
                name = source.doc["materials"][primitive["material"]]["name"]
                result.append((y, name))
    assert result, (x, z)
    return max(result)


def test_left_blue_cut_returns_the_forest_projection_to_waterside_ground():
    assert "Lake and garden soil" in terrain_samples(26.0, -3.1)[1]
    assert "Moss litter" in terrain_samples(26.0, -6.0)[1]


def test_right_blue_cut_ends_before_the_old_ring_following_tail():
    assert "Lake and garden soil" in terrain_samples(-23.0, 2.8)[1]
    assert "Moss litter" in terrain_samples(-21.9, 0.2)[1]


def test_flowerbed_belt_reaches_the_ring_without_crossing_neighbor_zones() -> None:
    for x, z in [
        (-24.0, 3.44),
        (-23.5, 3.12),
        (-23.0, 2.8),
        (-22.5, 2.49),
        (-22.0, 2.17),
        (-21.5, 1.86),
        (-21.25, 1.70),
    ]:
        assert "Lake and garden soil" in terrain_samples(x, z)[1], (x, z)
    assert "Warm meadow" in terrain_samples(-23.0, 4.6)[1]
    assert "Moss litter" in terrain_samples(-23.0, 1.5)[1]


def test_forest_has_no_separate_soil_collar_finish_or_extra_tree_mounds():
    source = ground()
    nodes = [
        node
        for node in source.doc["nodes"]
        if node.get("extras", {})
        .get("source_name", "")
        .startswith("COMPLETE Building garden island")
    ]
    forest = source.doc["extras"]["nest_ground_regions"]["forest"][0]
    for primitive in (
        p for node in nodes for p in source.doc["meshes"][node["mesh"]]["primitives"]
    ):
        name = source.doc["materials"][primitive["material"]]["name"]
        if "soil collar" not in name:
            continue
        points = _values(source, primitive["attributes"]["POSITION"])
        indices = [row[0] for row in _values(source, primitive["indices"])]
        for at in range(0, len(indices), 3):
            triangle = [points[i] for i in indices[at : at + 3]]
            x, _, z = [sum(p[k] for p in triangle) / 3 for k in range(3)]
            inside = False
            for a, b in zip(forest, forest[1:] + forest[:1]):
                if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (
                    b[1] - a[1]
                ) + a[0]:
                    inside = not inside
            assert not inside, (x, z, name)
    assert terrain_samples(-22.0, -13.0)[0] <= 0.57
    assert terrain_samples(16.5, -21.0)[0] <= 0.65


def test_landscape_stones_are_shared_prototypes_not_ground_geometry():
    assert not any(
        node.get("extras", {}).get("source_name")
        == "CY R003 finish LANDSCAPE grouped stones"
        for node in ground().doc["nodes"]
    )
    shared = _Model(str(NEST / "courtyard/parts/shared/shore-stones.glb"))
    prototypes = [
        node
        for node in shared.doc["nodes"]
        if node.get("extras", {}).get("stone_family") in {"block", "slab", "cut"}
    ]
    assert 0 < len(prototypes) < 40
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    parts = [
        part
        for area in ("forest-layout", "waterside-layout", "meadow-layout")
        for part in entries["view:" + area]["parts"]
    ]
    stone_paths = [
        path
        for part in parts
        if part["id"] == "source:shore-stones"
        for path in part["paths"]
    ]
    assert stone_paths and len(stone_paths) == len(set(stone_paths))
    assert not any(
        part["id"] == "source:shore-stones"
        for part in entries["view:courtyard-ground"]["parts"]
    )
