"""The flower library retains both complete approved four-component prototypes."""

import hashlib
from pathlib import Path

from test.godot.asset_geometry import read_glb

ROOT = Path(__file__).resolve().parents[3]


FLOWER_FAMILIES = (
    ("part_00005", "part_00006", "part_00007", "part_00008"),
    ("part_00012", "part_00013", "part_00014", "part_00015"),
)


def test_shared_flower_library_keeps_approved_complete_prototypes():
    path = ROOT / "godot_project/nest/courtyard/parts/shared/plant-library.glb"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "b9527b9035787b95b4d3cd9794dabb8fa9993d623488c5034564c816e9ed493b"
    )
    document, _ = read_glb(path)
    nodes = [n for n in document["nodes"] if "mesh" in n]
    assert len({n["name"] for n in nodes}) == len(nodes) == 16
    by_name = {node["name"]: node for node in nodes}
    for family, source_start in zip(FLOWER_FAMILIES, (57, 64)):
        for offset, (name, vertex_count) in enumerate(
            zip(family, (150, 810, 1140, 260))
        ):
            node = by_name[name]
            assert (
                node["extras"]["source_name"]
                == f"__ELFIE_INST_GROUP_{source_start + offset:03d}"
            )
            (primitive,) = document["meshes"][node["mesh"]]["primitives"]
            assert (
                document["accessors"][primitive["attributes"]["POSITION"]]["count"]
                == vertex_count
            )
