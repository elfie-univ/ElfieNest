"""The placed beds must retain the approved shared bed's real geometry."""

from collections import Counter
from pathlib import Path

from test.godot.asset_geometry import _Model

ROOT = Path(__file__).resolve().parents[3]
ESTATE = ROOT / "godot_project/nest/estate/ElfieNest-complete-final.glb"


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
    # Frozen accessor digests of the approved shared shell at HEAD 52db08c5.
    expected = [
        (
            (
                (
                    "NORMAL",
                    "0bf04b4da6cf1e18a148ef22b09f352f411fa1c716a13568687c9d93bcab9227",
                ),
                (
                    "POSITION",
                    "611ccf46a2869f93c20d8b39ba8ccb52f065de55c634b64b6fa7c20663386ef6",
                ),
            ),
            "727eca60d9f3d652ec57afdccc5a85c3be483e5f74565cfa08f880fc6afbf21c",
        ),
        (
            (
                (
                    "NORMAL",
                    "f9472053e332fe8c7db7c642fabf3dfb35b73b56f6018782f4e94d56fdeb37b6",
                ),
                (
                    "POSITION",
                    "a0ae643559f6a3607494e52e598e4f6c12b0d28a6bd35ca86e24aa05d4e53671",
                ),
            ),
            "f717f80eda9da4a57c2a487507fc157455bf099917f911f4fb261e43fb76ef06",
        ),
    ]
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
