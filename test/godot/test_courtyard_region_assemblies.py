"""Functional area previews show their complete geographically owned assembly."""

import json
from pathlib import Path

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import _triangles
from test.godot.test_courtyard_component_geometry import ground_height
from test.godot.test_lotus_bay import inside_polygon, point_segment

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"


def test_functional_area_menu_opens_totals_directly_except_the_two_forest_views():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    courtyard = next(
        row for row in index["fileGraph"]["categories"] if row["id"] == "courtyard"
    )
    areas = next(row for row in courtyard["children"] if row["id"] == "courtyard-areas")
    assert [row["id"] for row in areas["children"]] == [
        "view:courtyard-ground",
        "view:building-greenery",
        "forest",
        "view:waterside-layout",
        "view:meadow-layout",
    ]
    for row in areas["children"]:
        if row["id"] == "forest":
            assert [child["id"] for child in row["children"]] == [
                "view:forest-layout",
                "view:tree-one",
            ]
        else:
            assert "children" not in row


def test_central_greenery_has_one_assembly_and_is_not_embedded_in_ground():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    greenery = entries.get("view:building-greenery")
    assert greenery is not None
    assert greenery["file"] == "courtyard/areas/building/building-greenery.scn"
    assert (NEST / greenery["file"]).is_file()
    assert not greenery["focus"]
    assert "source:plant-library" in {part["id"] for part in greenery["parts"]}
    assert "source:plant-library" not in {
        part["id"] for part in entries["view:courtyard-ground"]["parts"]
    }
    assert "view:building-greenery" in {
        part["id"] for part in entries["view:courtyard-layout"]["parts"]
    }


def test_fountain_uses_its_glb_directly_from_waterside_without_a_scene_wrapper():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    assert "view:fountain" not in entries
    assert "view:fountain" not in index["previews"]
    assert not (
        NEST / "courtyard/areas/waterside/waterside-layout/fountain.scn"
    ).exists()
    for entry in entries.values():
        assert "view:fountain" not in {row["id"] for row in entry.get("parts", [])}
        assert "view:fountain" not in {row["id"] for row in entry.get("usedBy", [])}
    assert "source:fountain" in {
        row["id"] for row in entries["view:waterside-layout"]["parts"]
    }


def test_functional_area_entries_never_isolate_only_the_latest_added_parts():
    entries = json.loads((NEST / "assembly/asset-index.json").read_text())["fileGraph"][
        "entries"
    ]
    for area in (
        "courtyard-ground",
        "forest-layout",
        "waterside-layout",
        "meadow-layout",
    ):
        assert not entries["view:" + area].get("focus"), area


def test_each_area_references_its_own_real_ground_part_from_the_same_glb():
    entries = json.loads((NEST / "assembly/asset-index.json").read_text())["fileGraph"][
        "entries"
    ]
    model = _Model(str(NEST / "courtyard/parts/ground/shared-ground.glb"))
    bodies = [n for n in model.doc["nodes"] if n.get("extras", {}).get("ground_region")]
    assert {n["extras"]["ground_region"] for n in bodies} == {
        "ground",
        "forest",
        "waterside",
        "meadow",
    }
    for node in bodies:
        region = node["extras"]["ground_region"]
        asset = "courtyard-ground" if region == "ground" else region + "-layout"
        paths = [
            p
            for part in entries["view:" + asset]["parts"]
            if part["id"] == "source:shared-ground"
            for p in part["paths"]
        ]
        assert node["extras"]["v044_path"] in paths


def test_exposed_land_surfaces_follow_the_frozen_geographic_boundaries():
    model = _Model(str(NEST / "courtyard/parts/ground/shared-ground.glb"))
    polygons = model.doc["extras"]["nest_ground_regions"]
    identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for index, node in enumerate(model.doc["nodes"]):
        owner = node.get("extras", {}).get("ground_region")
        if not owner:
            continue
        polygon = polygons["building" if owner == "ground" else owner][0]
        for a, b, c in _triangles(model, index, identity):
            normal_y = (b[2] - a[2]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[2] - a[2])
            if (
                normal_y < 1e-8
                or min(a[1], b[1], c[1]) < -0.1
                or max(a[1], b[1], c[1]) - min(a[1], b[1], c[1]) > 1e-6
            ):
                continue
            for vertex in (a, b, c):
                point = (vertex[0], vertex[2])
                if inside_polygon(point, polygon):
                    continue
                distance = min(
                    point_segment(point, p, q)
                    for p, q in zip(polygon, polygon[1:] + polygon[:1])
                )
                # Independent paving still covers its original contact/support
                # faces. Test the exposed land rather than those hidden joins.
                assert (
                    distance <= 0.0001 or ground_height(*point) > vertex[1] + 0.001
                ), (owner, point)
