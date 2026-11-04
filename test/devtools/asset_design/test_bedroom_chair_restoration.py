"""All bedroom chairs retain their original, unexpanded V003 geometry."""

from collections import Counter

import pytest

from devtools.asset_design.shared_manifest import _Model
from test.devtools.asset_design.test_bed_shape_restoration import ROOT, _geometry

CHAIR = "shared_pod_petal_chair_d33b2e4ede"
BASE = f"devtools/asset_design/assets/furniture/{CHAIR}"


@pytest.mark.parametrize(
    "relative, copies",
    [
        (f"{BASE}/source/model.glb", 1),
        ("godot_project/rooms/estate/ElfieNest-complete-final.glb", 32),
    ],
)
def test_chair_petals_and_seams_match_original(relative, copies):
    original = _Model(str(ROOT / BASE / "versions/v003/model.glb"))
    expected = {
        node["extras"]["source_name"]: _geometry(original, node["mesh"])
        for node in original.doc["nodes"]
        if "mesh" in node
        and node.get("extras", {}).get("piece") in {"chair_petal", "chair_stitch"}
    }
    actual = _Model(str(ROOT / relative))
    seen = Counter()
    for node in actual.doc["nodes"]:
        extras = node.get("extras", {})
        name = extras.get("source_name")
        if "mesh" not in node or name not in expected:
            continue
        assert _geometry(actual, node["mesh"]) == expected[name], node["name"]
        seen[name] += 1
    assert seen == Counter(dict.fromkeys(expected, copies))
