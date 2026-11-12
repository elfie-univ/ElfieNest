"""Tree previews must select prototypes from their own formal GLB."""

import json
from pathlib import Path

from test.godot.asset_geometry import read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"


def test_split_tree_previews_keep_resolvable_focus_and_groups():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    for key, count in (
        ("source:broadleaf-tree", 1),
        ("source:pine-tree", 2),
        ("source:forest-twigs", 1),
    ):
        entry = index["fileGraph"]["entries"][key]
        document, _ = read_glb(NEST / entry["file"])
        available = {
            node.get("extras", {}).get("v044_path")
            for node in document["nodes"]
            if "mesh" in node
        }
        groups = index["previews"][key]["groups"]
        selected = [path for group in groups for path in group]
        assert len(selected) == len(set(selected)) == count, key
        assert set(selected) == set(entry["focus"]), key
        assert set(selected) <= available, key
