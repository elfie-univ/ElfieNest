"""Tree classes retain complete scenes and small shared shape sources."""

import json
from pathlib import Path

from test.godot.asset_geometry import read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"


def test_tree_classes_have_complete_scenes_and_bounded_geometry_sources():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    for key in ("view:branching-trees", "view:broadleaf-trees", "view:pine-trees"):
        entry = entries[key]
        assert (NEST / entry["file"]).is_file()
        assert entry["parts"]
    for file, limit in (
        ("tree-one.glb", 4_000_000),
        ("broadleaf-tree.glb", 3_000_000),
        ("pine-tree.glb", 1_000_000),
    ):
        assert (NEST / "courtyard/parts/forest" / file).stat().st_size < limit
    assert not (NEST / "courtyard/parts/forest/forest-wood.glb").exists()


def test_pine_branch_profiles_and_needles_have_one_owner():
    pine, _ = read_glb(NEST / "courtyard/parts/forest/pine-tree.glb")
    shared, _ = read_glb(NEST / "courtyard/parts/forest/forest-foliage.glb")
    profiles = [
        n
        for n in pine["nodes"]
        if n.get("extras", {}).get("pine_branch_profile", False)
    ]
    assert len(profiles) == 12
    assert len({n["mesh"] for n in profiles}) == 12
    needles = {f"__ELFIE_INST_GROUP_{i:03d}" for i in range(6)}
    assert {n.get("extras", {}).get("source_name") for n in pine["nodes"]} >= needles
    assert not (
        {n.get("extras", {}).get("source_name") for n in shared["nodes"]} & needles
    )


def test_pine_needles_and_fine_branches_use_matte_plant_materials():
    pine, _ = read_glb(NEST / "courtyard/parts/forest/pine-tree.glb")
    needles, twigs, trunks = set(), set(), set()
    for node in pine["nodes"]:
        extras = node.get("extras", {})
        if extras.get("pine_branch_profile"):
            target = twigs
        elif extras.get("tree_wood"):
            target = trunks
        elif extras.get("source_name", "").startswith("__ELFIE_INST_GROUP_"):
            target = needles
        else:
            continue
        target.update(
            primitive["material"]
            for primitive in pine["meshes"][node["mesh"]]["primitives"]
        )
    assert len(needles) == len(twigs) == len(trunks) == 1
    assert twigs.isdisjoint(trunks)
    needle, twig, trunk = (
        pine["materials"][next(iter(group))]["pbrMetallicRoughness"]
        for group in (needles, twigs, trunks)
    )
    assert needle["metallicFactor"] == twig["metallicFactor"] == 0.0
    assert needle["roughnessFactor"] >= 0.85 and twig["roughnessFactor"] >= 0.85
    red, green, blue, _ = needle["baseColorFactor"]
    assert green > max(red, blue)
    assert twig["baseColorFactor"][0] < trunk["baseColorFactor"][0] * 0.5


def test_branching_tree_group_references_two_whole_landmark_trees():
    entries = json.loads((NEST / "assembly/asset-index.json").read_text())["fileGraph"][
        "entries"
    ]
    group = "view:branching-trees"
    landmark = "view:tree-one"
    assert [(part["id"], part["count"]) for part in entries[group]["parts"]] == [
        (landmark, 2)
    ]
    assert [
        edge["count"] for edge in entries[landmark]["usedBy"] if edge["id"] == group
    ] == [2]
