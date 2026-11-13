"""Bedroom review names real components and keeps the lamp diffuser closed."""

import importlib
import json
import struct
from collections import Counter
from pathlib import Path

from test.godot.asset_geometry import read_glb

PROJECT = Path(__file__).resolve().parents[2] / "godot_project"
NEST = PROJECT / "nest"


def entries():
    return json.loads((NEST / "assembly/asset-index.json").read_text())["fileGraph"][
        "entries"
    ]


def test_bedroom_components_cover_visible_prototypes_and_have_sizes(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT / "tools"))
    sizes = importlib.import_module("review_asset_sizes")
    graph = entries()
    for asset, minimum in (
        ("bed-shared", 5),
        ("bedroom-cabinet", 4),
        ("bedroom-desks", 4),
    ):
        entry = graph["source:" + asset]
        components = entry["components"]
        assert len(components) >= minimum
        paths = [path for part in components for path in part["paths"]]
        assert len(paths) == len(set(paths))
        assert set(paths) == set(entry["focus"])
        sizes.glb_resources(
            NEST / entry["file"], components, lambda p: p.stat().st_size
        )
        assert all(part["size"]["meshBytes"] > 0 for part in components)


def test_bedroom_sets_reference_one_complete_bed():
    graph = entries()
    components = graph["source:bed-shared"]["components"]
    assert [part["title"] for part in components] == [
        "床体",
        "枕头",
        "被子",
        "花朵抱枕",
        "搭毯",
    ]
    for letter in "abcd":
        references = [
            row
            for row in graph["view:bedroom-set-" + letter]["parts"]
            if row["id"] == "source:bed-shared"
        ]
        assert len(references) == 1
        assert "component" not in references[0]
        assert len(set(references[0]["paths"])) == len(
            graph["source:bed-shared"]["focus"]
        )


def test_each_bedroom_set_lists_its_real_desktop():
    graph = entries()
    source = graph["source:bedroom-desks"]
    for letter in "abcd":
        rows = graph["view:bedroom-set-" + letter]["parts"]
        desktop = [row for row in rows if row.get("component") == "desktop-" + letter]
        assert len(desktop) == 1
        row = desktop[0]
        assert row["id"] == "source:bedroom-desks"
        component = next(
            part for part in source["components"] if part["id"] == row["component"]
        )
        assert row["targetPaths"] == component["paths"]
        assert len(row["paths"]) == 2
        assert all("/" + letter.upper() + " |" in path for path in row["paths"])
        cabinet = [row for row in rows if row["id"] == "source:bedroom-cabinet"]
        assert len(cabinet) == 1
        assert "component" not in cabinet[0]
        assert len(cabinet[0]["paths"]) == 7


def test_all_glbs_reconcile_their_file_breakdowns(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT / "tools"))
    graph = entries()
    sizes = importlib.import_module("review_asset_sizes")
    sizes.add_asset_sizes(graph, NEST)
    for entry in graph.values():
        size = entry["size"]
        references = size.get("referenceFiles", [])
        assert sum(row["bytes"] for row in references) == size["referenceBytes"]
        assert len({row["path"] for row in references}) == len(references)
        if not entry["file"].endswith(".glb"):
            continue
        assert sum(size["breakdown"].values()) == size["fileBytes"], entry["file"]
        assert min(size["breakdown"].values()) >= 0, entry["file"]


def test_building_does_not_reference_the_wall_niche_libraries_directly():
    graph = entries()
    building = graph["view:building-layout"]
    assert not {"source:main-decor", "source:main-planters"} & {
        row["id"] for row in building["parts"]
    }


def test_table_library_keeps_independent_uses_and_one_reverse_link():
    graph = entries()
    living = [
        row
        for row in graph["view:central-living"]["parts"]
        if row["id"] == "source:main-tables"
    ]
    assert [(row["title"], row["count"]) for row in living] == [
        ("高橡木茶几", 2),
        ("橡木边几", 1),
    ]
    reverse = [
        row
        for row in graph["source:main-tables"]["usedBy"]
        if row["id"] == "view:central-living"
    ]
    assert len(reverse) == 1
    assert set(reverse[0]["targetPaths"]) == {
        path for row in living for path in row["paths"]
    }


def test_bed_size_breakdown_reconciles_with_the_file(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT / "tools"))
    graph = entries()
    entry = graph["source:bed-shared"]
    _, breakdown = importlib.import_module("review_asset_sizes").glb_resources(
        NEST / entry["file"],
        entry["components"],
        lambda path: path.stat().st_size,
    )
    assert sum(breakdown.values()) == (NEST / entry["file"]).stat().st_size
    assert breakdown["componentMeshBytes"] == sum(
        part["size"]["meshBytes"] for part in entry["components"]
    )
    assert breakdown["variantMeshBytes"] == 0
    assert breakdown["otherMeshBytes"] == 0


def test_bed_upholstery_and_welt_are_closed_single_sided_surfaces():
    document, binary = read_glb(NEST / "furniture/shared/bedroom/bed-shared.glb")
    names = {
        "A | Bed | continuous scalloped sage upholstery",
        "A | Bed | continuous upholstery welt",
    }
    meshes = {
        node["mesh"]
        for node in document["nodes"]
        if node.get("extras", {}).get("source_name") in names
    }
    assert len(meshes) >= len(names)

    def read_rows(index, row_format):
        accessor = document["accessors"][index]
        view = document["bufferViews"][accessor["bufferView"]]
        offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        row = struct.Struct(row_format)
        stride = view.get("byteStride", row.size)
        return [
            row.unpack_from(binary, offset + i * stride)
            for i in range(accessor["count"])
        ]

    for mesh in meshes:
        primitive = document["meshes"][mesh]["primitives"][0]
        material = document["materials"][primitive["material"]]
        assert not material.get("doubleSided", False)
        points = read_rows(primitive["attributes"]["POSITION"], "<3f")
        indices = read_rows(primitive["indices"], "<H")
        vertices = [points[index] for (index,) in indices]
        edges = Counter()
        for a, b, c in zip(vertices[::3], vertices[1::3], vertices[2::3]):
            edges.update(((a, b), (b, c), (c, a)))
        assert all(count == edges[b, a] == 1 for (a, b), count in edges.items())


def test_lamp_shell_is_closed_opaque_and_emissive():
    document, binary = read_glb(NEST / "furniture/shared/bedroom/bedroom-lamps.glb")
    node = next(
        n
        for n in document["nodes"]
        if n.get("extras", {}).get("source_name") == "A | Desk | amber globe"
    )
    primitive = document["meshes"][node["mesh"]]["primitives"][0]
    material = document["materials"][primitive["material"]]
    assert material.get("alphaMode", "OPAQUE") == "OPAQUE"
    assert material["pbrMetallicRoughness"]["baseColorFactor"][3] == 1
    assert (
        material["extensions"]["KHR_materials_emissive_strength"]["emissiveStrength"]
        > 0
    )
    assert node["extras"]["nest_materials"][0]["transparency"] == 0
    accessor = document["accessors"][primitive["indices"]]
    view = document["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = struct.unpack_from("<" + "H" * accessor["count"], binary, offset)
    edges = Counter()
    for i in range(0, len(values), 3):
        a, b, c = values[i : i + 3]
        assert len({a, b, c}) == 3
        for x, y in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted((x, y)))] += 1
    assert set(edges.values()) == {2}
