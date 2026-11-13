"""Landing posts reuse the main building's authored rail-post prototype."""

import json
from pathlib import Path

from test.godot.asset_geometry import read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"
POSTS = ("LandingTerminalPostInner", "LandingTerminalPostOuter")


def test_landing_posts_share_the_original_building_post_mesh_and_material():
    doc, _ = read_glb(NEST / "buildings/main/central-building.glb")
    nodes = {
        node.get("extras", {}).get("source_name"): node
        for node in doc["nodes"]
        if "mesh" in node
    }
    prototype = nodes["Public stair rail post"]
    for name in POSTS:
        assert name in nodes, name
        assert nodes[name]["mesh"] == prototype["mesh"]


def test_landing_posts_belong_to_the_building_assembly_and_leave_the_forest():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    assert "source:forest-trail-fixtures" not in entries
    assert not (
        NEST / "courtyard/areas/forest/forest-layout/forest-trail-fixtures.glb"
    ).exists()
    part = next(
        row
        for row in entries["view:building-layout"]["parts"]
        if row["id"] == "source:central-building"
    )
    for name in POSTS:
        path = f"Generated/CompleteEstate/{name}"
        assert path in part["paths"]
        assert all(
            path not in row.get("paths", [])
            for row in entries["view:forest-layout"]["parts"]
        )
