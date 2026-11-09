"""Check the accepted ground, stone-wall prototypes and coplanar water inputs."""

import hashlib
from functools import lru_cache

import pytest

from test.godot.estate_assets.test_pod_desktop_contacts import (
    ROOT,
    _triangles,
)
from test.godot.formal_asset_geometry import NamedModel as _Model

IDENTITY = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
# The approved shore cleanup replaced the old lake banks with these ground regions.
BANKS = (
    "COMPLETE Building garden island",
    "COMPLETE Building garden island • forest",
    "COMPLETE Building garden island • waterside",
    "COMPLETE Building garden island • meadow",
)
GROUND = "godot_project/nest/courtyard/parts/ground/shared-ground.glb"
FOUNTAIN = "godot_project/nest/courtyard/parts/waterside/fountain.glb"
LAKE = "godot_project/nest/courtyard/parts/waterside/lake.glb"


@lru_cache(maxsize=2)
def _model(path):
    return _Model(str(ROOT / path))


@pytest.mark.parametrize(
    "path",
    [
        GROUND,
    ],
)
def test_waterfall_has_no_exposed_footing_fins_or_soil(path):
    model = _model(path)
    for side in ("north", "south"):
        name = f"CY R001 spillway receiving {side} bank footing"
        assert not any(
            node.get("name") == name and "mesh" in node
            for node in _model(FOUNTAIN).doc["nodes"]
        ), name
    # The clearance spans the actual outer faces of both stone walls and the
    # falling sheet. Test triangle samples, including edges, rather than AABBs.
    count = 0
    for i, node in enumerate(model.doc["nodes"]):
        if node.get("name") not in BANKS or "mesh" not in node:
            continue
        count += 1
        for triangle in _triangles(model, i, IDENTITY):
            for weights in (
                (1 / 3, 1 / 3, 1 / 3),
                (0.5, 0.5, 0),
                (0, 0.5, 0.5),
                (0.5, 0, 0.5),
            ):
                x, y, z = [
                    sum(p[k] * w for p, w in zip(triangle, weights)) for k in range(3)
                ]
                assert not (
                    24.781 < x < 25.799 and 27.5946 < z < 30.1526 and y > -0.39
                ), (node["name"], x, y, z)
    assert count == len(BANKS)


APPROVED_WATERSIDE = {
    GROUND: "fa9104e82e46d3e35442ec75947f1f9d80ac07285a22244297a03784357c9fe7",
    FOUNTAIN: "fcc71e5930ff223b97bb059337d9c6d810a9dee965a254d62f9e502591dccff3",
    LAKE: "1c1b342d9968d1e0395d8a6f1984050acce8d82a4f1c6eb92c9a73835f32772e",
}


def _approved_waterside():
    # Old merged earth boxes are not the approved split shore topology. These
    # frozen inputs plus native world contacts protect that approved visual work.
    for relative, digest in APPROVED_WATERSIDE.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    return _model(GROUND), _model(FOUNTAIN), _model(LAKE)


def test_waterfall_shoulders_keep_the_approved_ground_regions():
    ground, fountain, _ = _approved_waterside()
    regions = {
        n["name"]: n["extras"]["ground_region"]
        for n in ground.doc["nodes"]
        if n.get("name") in BANKS and "mesh" in n
    }
    assert set(regions) == set(BANKS)
    assert set(regions.values()) == {"ground", "forest", "waterside", "meadow"}
    for side in ("north", "south"):
        assert (
            sum(
                n.get("name") == f"CY R001 spillway {side} continuous side wall"
                and "mesh" in n
                for n in fountain.doc["nodes"]
            )
            == 1
        )


def test_waterfall_opening_keeps_the_approved_water_contact():
    _, fountain, lake = _approved_waterside()
    surfaces = (
        (lake, "COMPLETE Inset natural lake"),
        (fountain, "COMPLETE Inset natural lake receiving under spillway"),
    )
    heights = []
    for model, name in surfaces:
        (index,) = [
            i for i, n in enumerate(model.doc["nodes"]) if n.get("name") == name
        ]
        heights.extend(
            p[1] for triangle in _triangles(model, index, IDENTITY) for p in triangle
        )
    assert heights and max(heights) - min(heights) < 1e-7
    assert abs(heights[0] + 0.39) < 1e-7
