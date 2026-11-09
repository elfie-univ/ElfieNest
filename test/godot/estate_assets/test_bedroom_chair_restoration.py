"""The accepted shared chair prototype retains all approved petals and seams.

The 32 placed instances are verified by test_split_runtime.gd.
"""

from collections import Counter

from test.godot.formal_asset_geometry import NamedModel, assert_approved_source

EXPECTED_NAMES = (
    "Chair | central tall back petal",
    "Chair | central tall back petal tailored inner seam",
    "Chair | left back petal",
    "Chair | left back petal tailored inner seam",
    "Chair | left cupped arm petal",
    "Chair | left cupped arm petal tailored inner seam",
    "Chair | right back petal",
    "Chair | right back petal tailored inner seam",
    "Chair | right cupped arm petal",
    "Chair | right cupped arm petal tailored inner seam",
)


def test_chair_petals_and_seams_match_accepted_split_prototype():
    path = assert_approved_source("furniture/shared/bedroom/chair.glb")
    model = NamedModel(str(path))
    seen = Counter(
        node.get("extras", {}).get("source_name")
        for node in model.doc["nodes"]
        if "mesh" in node
        and node.get("extras", {}).get("source_name") in EXPECTED_NAMES
    )
    assert seen == Counter(dict.fromkeys(EXPECTED_NAMES, 1))
