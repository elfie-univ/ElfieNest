"""Regression checks for the reported cushion, painting and ceiling contacts."""

import math
from functools import lru_cache

import pytest

from test.godot.estate_assets.test_pod_desktop_contacts import ROOT, _point, _values
from test.godot.formal_asset_geometry import NamedModel as _Model


@lru_cache
def _model(relative):
    return _Model(str(ROOT / relative))


def _primitives(model, index):
    return model.doc["meshes"][model.doc["nodes"][index]["mesh"]]["primitives"]


@pytest.mark.parametrize(
    "relative",
    [
        "godot_project/nest/buildings/pod/pod-building.glb",
    ],
)
def test_bedroom_strip_touches_the_actual_ceiling(relative):
    model = _model(relative)
    for module in ["M01"]:
        nodes = {
            node["name"].split(" | ")[-1].removesuffix("_001"): index
            for index, node in enumerate(model.doc["nodes"])
            if "mesh" in node and node.get("extras", {}).get("module") == module
        }
        lamp = nodes["ROOM • closed ceiling light"]
        slab = nodes["ROOM • structural terrace slab"]
        lamp_top = max(
            point[1]
            for primitive in _primitives(model, lamp)
            for point in _values(model, primitive["attributes"]["POSITION"])
        )
        ceiling = min(
            point[1]
            for primitive in _primitives(model, slab)
            for point in _values(model, primitive["attributes"]["POSITION"])
        )
        assert abs(lamp_top - ceiling) < 0.001, (module, ceiling - lamp_top)


@pytest.mark.parametrize(
    "relative",
    [
        "godot_project/nest/furniture/layouts/terraces/terrace-layout-06-local.glb",
    ],
)
def test_botanical_painting_has_its_stem_at_the_bottom(relative):
    model = _model(relative)
    index = next(
        index
        for index, node in enumerate(model.doc["nodes"])
        if node.get("name") == "botanical_painting_easel" and "mesh" in node
    )
    primitive = _primitives(model, index)[2]
    points = [
        _point(model.world(index), point)
        for point in _values(model, primitive["attributes"]["POSITION"])
    ]
    lower = min(point[1] for point in points)
    upper = max(point[1] for point in points)
    bottom = [point for point in points if point[1] < lower + 0.02]
    top = [point for point in points if point[1] > upper - 0.02]
    bottom_width = math.hypot(
        max(point[0] for point in bottom) - min(point[0] for point in bottom),
        max(point[2] for point in bottom) - min(point[2] for point in bottom),
    )
    top_width = math.hypot(
        max(point[0] for point in top) - min(point[0] for point in top),
        max(point[2] for point in top) - min(point[2] for point in top),
    )
    assert bottom_width < 0.035, "The exposed stem points upward"
    assert top_width > 0.06, "The leaves are still upside down"
