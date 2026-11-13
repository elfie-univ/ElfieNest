"""The courtyard glazing starts inside the solid wall cap, not at ground level."""

import math
from pathlib import Path

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import (
    _point,
    _radii,
    _section,
    _triangles,
    _values,
)

PARTS = (
    Path(__file__).resolve().parents[2] / "godot_project/nest/courtyard/parts/ground"
)
IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def test_glazing_lower_edge_is_embedded_in_the_wall_cap():
    ground = _Model(str(PARTS / "shared-ground.glb"))
    cover = _Model(str(PARTS / "courtyard-cover.glb"))
    cap = next(
        i
        for i, node in enumerate(ground.doc["nodes"])
        if node.get("extras", {}).get("source_name")
        == "Preview shallow limestone wall cap"
    )
    glass = next(
        i
        for i, node in enumerate(cover.doc["nodes"])
        if node.get("extras", {}).get("source_name")
        == "Original courtyard wall extended vertically R50 centerZ6"
    )
    points = [
        _point(cover.world(glass), point)
        for primitive in cover.doc["meshes"][cover.doc["nodes"][glass]["mesh"]][
            "primitives"
        ]
        for point in _values(cover, primitive["attributes"]["POSITION"])
    ]
    bottom = min(point[1] for point in points)
    cap_faces = list(_triangles(ground, cap, IDENTITY))
    cap_heights = [point[1] for triangle in cap_faces for point in triangle]
    assert min(cap_heights) + 0.01 < bottom < max(cap_heights) - 0.01
    segments = [
        [(x, z - 6.0) for x, z in segment] for segment in _section(cap_faces, bottom)
    ]
    edge = {(x, y, z) for x, y, z in points if abs(y - bottom) < 1e-6}
    assert len(edge) >= 128
    for x, _, z in edge:
        radii = _radii(segments, math.atan2(z - 6.0, x))
        radius = math.hypot(x, z - 6.0)
        assert len(radii) >= 2
        assert min(radii) + 0.01 < radius < max(radii) - 0.01
