"""The placed beds must retain the approved shared bed's real geometry."""

from pathlib import Path

from test.godot.formal_asset_geometry import NamedModel as _Model
from test.godot.formal_asset_geometry import assert_approved_source

ROOT = Path(__file__).resolve().parents[3]
ESTATE = ROOT / "godot_project/nest/furniture/shared/bedroom/bed-shared.glb"


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


def test_shared_bed_shell_matches_accepted_split_prototype():
    # Frozen before this runtime migration, when the user accepted the split view.
    assert_approved_source("furniture/shared/bedroom/bed-shared.glb")
    model = _Model(str(ESTATE))
    shells = [
        node
        for node in model.doc["nodes"]
        if "mesh" in node
        and node.get("extras", {}).get("assembly") == "bed"
        and node.get("extras", {}).get("piece") == "shell"
    ]
    assert len(shells) == 1
    assert shells[0]["extras"]["resident"] == "A"
    # Four slots in each of eight rooms reuse this prototype; the native runtime
    # fixture checks every placed bed and its independent interaction identity.
