"""The placed beds must retain the approved shared bed's real geometry."""

from pathlib import Path

from test.godot.formal_asset_geometry import NamedModel as _Model
from test.godot.formal_asset_geometry import assert_approved_source

ROOT = Path(__file__).resolve().parents[3]
ESTATE = ROOT / "godot_project/nest/furniture/shared/bedroom/bed-shared.glb"


def test_shared_bed_shell_matches_accepted_split_prototype():
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
