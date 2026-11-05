from pathlib import Path

import pytest

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import (
    _section,
    _triangles,
    _values,
)

ROOT = Path(__file__).resolve().parents[3]
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
@pytest.mark.parametrize("height", [0.8, 1.5, 2.3])
def test_glass_edge_reaches_garden_entrance_frame(path, height):
    model = _Model(str(ROOT / path))
    segments = {}
    for name in ("Central L1 rounded garden entrance", "Central L1 curved front glass"):
        index = next(
            i for i, node in enumerate(model.doc["nodes"]) if node.get("name") == name
        )
        segments[name] = _section(list(_triangles(model, index, IDENTITY)), height)
    for side in (-1, 1):
        glass = [
            point
            for segment in segments["Central L1 curved front glass"]
            for point in segment
            if abs(point[0] - side * 1.45) < 0.001
        ]
        assert glass, "Missing glass boundary"
        x = side * 1.45
        frame_hits = [
            a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
            for a, b in segments["Central L1 rounded garden entrance"]
            if abs(b[0] - a[0]) > 1e-9 and min(a[0], b[0]) <= x <= max(a[0], b[0])
        ]
        assert frame_hits, "Missing frame section"
        gap = min(frame_hits) - max(point[1] for point in glass)
        assert gap <= 0.002, f"Glass/frame gap {gap * 1000:.1f} mm at {height} m"


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_curved_glass_edge_has_no_sudden_depth_step(path):
    model = _Model(str(ROOT / path))
    node = next(
        node
        for node in model.doc["nodes"]
        if node.get("name") == "Central L1 curved front glass"
    )
    checked = 0
    for primitive in model.doc["meshes"][node["mesh"]]["primitives"]:
        points = _values(model, primitive["attributes"]["POSITION"])
        normals = _values(model, primitive["attributes"]["NORMAL"])
        for (x, y, z), normal in zip(points, normals):
            if 2.48 <= y <= 2.78 and 1.04 < abs(x) <= 1.451 and normal[2] > 0.9:
                checked += 1
                assert z >= 8.530, (
                    f"Curved glass edge falls short of frame: x={x:.2f}, y={y:.2f}, z={z:.3f}"
                )
    assert checked
