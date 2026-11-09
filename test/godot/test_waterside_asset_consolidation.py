"""Water features keep their rendering inputs while sharing complete asset files."""

import hashlib
import json
from pathlib import Path

import pytest

from test.godot.asset_geometry import _Model

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"
OBSOLETE = {
    "source:waterfall": "courtyard/parts/waterside/waterfall.glb",
    "view:waterfall": "courtyard/areas/waterside/waterside-layout/waterfall.scn",
    "source:water-lilies": "courtyard/areas/waterside/waterside-layout/water-lilies.glb",
}


def render_rows(path):
    source = _Model(str(path))
    rows = []
    for i, node in enumerate(source.doc["nodes"]):
        if "mesh" not in node:
            continue
        primitives = json.loads(json.dumps(source.doc["meshes"][node["mesh"]]))
        for primitive in primitives["primitives"]:
            primitive["attributes"] = {
                key: source.accessor(value)
                for key, value in primitive["attributes"].items()
            }
            if "indices" in primitive:
                primitive["indices"] = source.accessor(primitive["indices"])
            if "material" in primitive:
                primitive["material"] = source.doc["materials"][primitive["material"]]
        rows.append(
            json.dumps(
                {
                    "extras": node.get("extras", {}),
                    "matrix": source.world(i),
                    "mesh": primitives,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return rows


def digest(rows):
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def test_water_features_have_two_complete_source_entries():
    index = json.loads((NEST / "assembly/asset-index.json").read_text())
    entries = index["fileGraph"]["entries"]
    for key, file in OBSOLETE.items():
        assert key not in entries
        assert key not in index["previews"]
        assert not (NEST / file).exists()
        assert not (NEST / (file + ".import")).exists()
    for entry in entries.values():
        assert not ({part["id"] for part in entry.get("parts", [])} & OBSOLETE.keys())
    assert entries["source:fountain"]["title"] == "喷泉、水道与瀑布"
    assert entries["source:lake"]["title"] == "湖面与荷花"
    for key in ("source:fountain", "source:lake"):
        model = _Model(str(NEST / entries[key]["file"]))
        visible = {
            node["extras"]["v044_path"]
            for node in model.doc["nodes"]
            if "mesh" in node and node["extras"].get("review_visible", True)
        }
        assert set(entries[key]["focus"]) == visible


@pytest.mark.parametrize(
    "file,count,adjusted_water,expected",
    [
        (
            "courtyard/parts/waterside/fountain.glb",
            81,
            "COMPLETE Inset natural lake receiving under spillway",
            "cadfcb30abd489de06be92902ca1149eaf34a529b19513945c234ff5075a741f",
        ),
    ],
)
def test_consolidation_preserves_every_mesh_corner_material_and_pose(
    file, count, adjusted_water, expected
):
    rows = render_rows(NEST / file)
    assert len(rows) == count
    # The receiving contour follows the physical-bank fit contract. The approved
    # replacement of the old lily prototypes is covered by test_lotus_bay.
    unchanged = [
        row
        for row in rows
        if json.loads(row)["extras"]["source_name"] != adjusted_water
    ]
    assert digest(unchanged) == expected
