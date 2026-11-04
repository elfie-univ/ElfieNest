"""The placed beds must retain the approved shared bed's real geometry."""

from collections import Counter
from pathlib import Path

from devtools.asset_design.shared_manifest import _Model

ROOT = Path(__file__).resolve().parents[3]
MASTER = (
    ROOT
    / "devtools/asset_design/assets/furniture/shared_pod_bed_b250b4cffd/source/model.glb"
)
LAYOUT = ROOT / "devtools/asset_design/assets/layouts/pod_bedroom/source/model.glb"
ESTATE = ROOT / "godot_project/rooms/estate/ElfieNest-complete-final.glb"


def _geometry(model, mesh_index):
    return [
        (
            tuple(
                (name, model.accessor(index)["bytes"])
                for name, index in sorted(primitive["attributes"].items())
            ),
            model.accessor(primitive["indices"])["bytes"]
            if "indices" in primitive
            else None,
        )
        for primitive in model.doc["meshes"][mesh_index]["primitives"]
    ]


def test_all_32_runtime_bed_shells_match_the_shared_original():
    master = _Model(str(MASTER))
    original = next(
        node
        for node in master.doc["nodes"]
        if node.get("extras", {}).get("source_name")
        == "Bed | complete independent pod shell"
        and "mesh" in node
    )
    expected = _geometry(master, original["mesh"])
    estate = _Model(str(ESTATE))
    shells = [
        node
        for node in estate.doc["nodes"]
        if node.get("extras", {}).get("assembly") == "bed"
        and node.get("extras", {}).get("piece") == "shell"
        and "mesh" in node
    ]
    assert Counter(node["extras"]["module"] for node in shells) == {
        f"M{number:02d}": 4 for number in range(1, 9)
    }
    for node in shells:
        assert _geometry(estate, node["mesh"]) == expected, node["name"]


def test_bedroom_layout_uses_the_shared_shell_for_all_four_beds():
    layout = _Model(str(LAYOUT))
    bindings = [
        binding
        for instance in layout.doc["extras"]["templateInstances"]
        if instance.get("object") == "part:shared_pod_bed_b250b4cffd"
        for binding in instance["bindings"]
        if binding.get("properties", {}).get("piece") == "shell"
    ]
    assert {binding["properties"]["resident"] for binding in bindings} == set("ABCD")
    assert len(bindings) == 4
