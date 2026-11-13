"""Shared building prototypes retain distinct placements and editable parts."""

import importlib
import json
import struct
from pathlib import Path

import pytest

from test.godot.asset_geometry import read_glb

BUILDINGS = Path(__file__).resolve().parents[2] / "godot_project/nest/buildings"


def test_pod_door_lining_stays_inside_the_floor_thickness():
    doc, _ = read_glb(BUILDINGS / "pod/pod-building.glb")
    nodes = {node.get("extras", {}).get("source_name"): node for node in doc["nodes"]}
    lining = nodes["M01 | ROOM • complete rear door lining_001"]
    floor = nodes["M01 | ROOM • continuous lower floor_001"]
    assert all(
        lining.get(key) == floor.get(key)
        for key in ("matrix", "translation", "rotation", "scale")
    )

    def height_bounds(node):
        return [
            doc["accessors"][part["attributes"]["POSITION"]]
            for part in doc["meshes"][node["mesh"]]["primitives"]
        ]

    floor_bottom = min(part["min"][1] for part in height_bounds(floor))
    assert all(part["min"][1] > floor_bottom for part in height_bounds(lining))


def test_pod_connector_underside_meets_the_room_without_a_step():
    doc, binary = read_glb(BUILDINGS / "pod/pod-building.glb")
    floor = next(
        node
        for node in doc["nodes"]
        if node.get("extras", {}).get("source_name")
        == "M01 | ROOM • continuous lower floor_001"
    )
    part = doc["meshes"][floor["mesh"]]["primitives"][0]
    points = doc["accessors"][part["attributes"]["POSITION"]]
    view = doc["bufferViews"][points["bufferView"]]
    start = view.get("byteOffset", 0) + points.get("byteOffset", 0)
    coords = list(
        struct.iter_unpack("<3f", binary[start : start + points["count"] * 12])
    )
    join = [y for x, y, z in coords if abs(z + 2.36) < 1e-5 and abs(x) <= 2.461]
    assert min(join) == pytest.approx(0.19)
    assert max(join) == pytest.approx(0.30)


def test_main_building_inspector_measures_shared_door_and_window_meshes(monkeypatch):
    nest = BUILDINGS.parent
    monkeypatch.syspath_prepend(str(nest.parent / "tools"))
    size = importlib.import_module("review_asset_sizes")
    entries = json.loads((nest / "assembly/asset-index.json").read_text())["fileGraph"][
        "entries"
    ]
    entry = entries["source:central-building"]
    size.glb_resources(
        nest / entry["file"], entry["components"], lambda p: p.stat().st_size
    )
    parts = {part["id"]: part for part in entry["components"]}
    doors = parts["bedroom-sliding-door"]
    bindings = json.loads((nest / "assembly/runtime-bindings.json").read_text())[
        "placements"
    ]
    assert set(doors["paths"]) == {
        path for path, extras in bindings.items() if extras.get("door_prototype")
    }
    for key, instances in (
        ("bedroom-sliding-door", 8),
        ("floor-2-glass", 4),
        ("floor-3-glass", 4),
        ("roof-petals", 3),
    ):
        assert parts[key]["size"]["instances"] == instances
        assert parts[key]["size"]["meshCopies"] == 1
    posts = parts["stair-posts"]["size"]
    assert 1 <= posts["meshCopies"] < posts["instances"]


def test_each_floor_uses_one_curved_glass_and_reveal_prototype():
    doc, _ = read_glb(BUILDINGS / "main/central-building.glb")
    by_name = {node.get("extras", {}).get("source_name"): node for node in doc["nodes"]}
    for floor in (2, 3):
        for component in ("curved glass", "fitted reveal"):
            nodes = [
                by_name[f"Central L{floor} {component} quadrant {quadrant}"]
                for quadrant in range(1, 5)
            ]
            primitives = [
                doc["meshes"][node["mesh"]]["primitives"][0] for node in nodes
            ]
            assert len({part["indices"] for part in primitives}) == 1
            for semantic in ("POSITION", "NORMAL"):
                assert len({part["attributes"][semantic] for part in primitives}) == 1
            assert len({tuple(node["matrix"]) for node in nodes}) == 4


def test_roof_petals_share_shell_and_light_channel_geometry():
    doc, _ = read_glb(BUILDINGS / "main/central-building.glb")
    nodes = [
        node
        for node in doc["nodes"]
        if node.get("extras", {}).get("source_name", "").startswith("Roof01 petal ")
        and node.get("extras", {})
        .get("source_name", "")
        .endswith(" shell and light channels")
    ]
    assert len(nodes) == 3
    for slot in (0, 1):
        parts = [doc["meshes"][node["mesh"]]["primitives"][slot] for node in nodes]
        assert len({part["attributes"]["POSITION"] for part in parts}) == 1
        assert len({part["indices"] for part in parts}) == 1
