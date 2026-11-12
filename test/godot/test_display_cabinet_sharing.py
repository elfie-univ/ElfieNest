"""The display cabinet keeps placed parts while reusing their stored geometry."""

import importlib
import json
from pathlib import Path

from test.godot.asset_geometry import read_glb

PROJECT = Path(__file__).resolve().parents[2] / "godot_project"
NEST = PROJECT / "nest"


def test_cabinet_panel_counts_real_shared_shapes(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT / "tools"))
    sizes = importlib.import_module("review_asset_sizes")
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    cabinet = entries["source:central-games-cabinet"]
    model = NEST / cabinet["file"]
    sizes.glb_resources(model, cabinet["components"], lambda path: path.stat().st_size)
    parts = {row["id"]: row for row in cabinet["components"]}
    for name, count in (
        ("doors", 8),
        ("upright-books", 16),
        ("stacked-books", 3),
        ("houses", 3),
        ("rainbows", 2),
    ):
        assert parts[name]["size"]["instances"] == count
        assert parts[name]["size"]["meshCopies"] == 1

    document, _ = read_glb(model)
    by_path = {
        node["extras"]["v044_path"]: node
        for node in document["nodes"]
        if "mesh" in node
    }
    assert set(by_path) == set(cabinet["focus"])
    reference = next(
        row
        for row in entries["view:central-layout-2"]["parts"]
        if row["id"] == "source:central-games-cabinet"
    )
    assert set(reference["paths"]) == set(by_path)
    books = [
        document["meshes"][by_path[path]["mesh"]]
        for path in parts["upright-books"]["paths"]
    ]
    assert len({book["primitives"][0]["material"] for book in books}) == 2
    assert len({book["primitives"][0]["attributes"]["POSITION"] for book in books}) == 1

    rainbow = document["meshes"][by_path[parts["rainbows"]["paths"][0]]["mesh"]]
    assert all(
        set(primitive["attributes"]) == {"POSITION", "NORMAL"}
        for primitive in rainbow["primitives"]
    )
