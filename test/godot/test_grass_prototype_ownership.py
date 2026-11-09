"""The grass tuft belongs to shared plants without losing regional references."""

import json
from pathlib import Path

from test.godot.asset_geometry import read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"
GRASS = "__ELFIE_INST_GROUP_030"


def grass_path(path):
    return GRASS in path


def test_grass_prototype_is_in_shared_plants_and_not_in_tree_leaves():
    plants, _ = read_glb(NEST / "courtyard/parts/shared/plant-library.glb")
    leaves, _ = read_glb(NEST / "courtyard/parts/forest/forest-foliage.glb")
    plant_nodes = [n for n in plants["nodes"] if "mesh" in n]
    leaf_nodes = [n for n in leaves["nodes"] if "mesh" in n]
    assert (
        sum(n.get("extras", {}).get("source_name") == GRASS for n in plant_nodes) == 1
    )
    assert all(n.get("extras", {}).get("source_name") != GRASS for n in leaf_nodes)


def test_all_regional_grass_references_and_preview_use_shared_plants():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    references = []
    for area in ("forest", "meadow", "waterside"):
        entry = index["fileGraph"]["entries"][f"view:{area}-layout"]
        plants = next(p for p in entry["parts"] if p["id"] == "source:plant-library")
        leaves = next(p for p in entry["parts"] if p["id"] == "source:forest-foliage")
        grass = [p for p in plants["paths"] if grass_path(p)]
        assert grass, area
        assert not any(grass_path(p) for p in leaves["paths"]), area
        references.extend(grass)
    assert len(references) == len(set(references)) == 38
    previews = index["previews"]
    assert any(
        grass_path(p) for row in previews["source:plant-library"]["groups"] for p in row
    )
    assert not any(
        grass_path(p)
        for row in previews["source:forest-foliage"]["groups"]
        for p in row
    )
