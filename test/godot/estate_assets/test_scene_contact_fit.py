"""Contacts must be checked against the visible solids, including shared mothers."""

from functools import lru_cache
from pathlib import Path

import pytest

from test.godot.asset_geometry import _Model
from test.godot.estate_assets.test_pod_desktop_contacts import _point, _values

ROOT = Path(__file__).resolve().parents[3]


@lru_cache
def model(path):
    return _Model(str(ROOT / path))


def mesh_points(m, index, material=None):
    for primitive in m.doc["meshes"][m.doc["nodes"][index]["mesh"]]["primitives"]:
        if (
            material
            and material not in m.doc["materials"][primitive["material"]]["name"]
        ):
            continue
        for point in _values(m, primitive["attributes"]["POSITION"]):
            yield _point(m.world(index), point)


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_reading_chair_legs_meet_the_seat(path):
    m = model(path)
    index = next(
        i
        for i, n in enumerate(m.doc["nodes"])
        if n.get("name") == "quiet_rear_reading_armchair" and "mesh" in n
    )
    wood = list(mesh_points(m, index, "oak"))
    seat = list(mesh_points(m, index, "upholstery"))
    assert max(p[1] for p in wood) >= min(p[1] for p in seat) + 0.002, (
        "Chair legs end below the seat"
    )


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_desk_lens_is_vertical_on_the_rear_board(path):
    m = model(path)
    index = next(
        i
        for i, n in enumerate(m.doc["nodes"])
        if n.get("name") == "Draft L3 writing desk concealed downward task lens"
    )
    ps = list(mesh_points(m, index))
    assert max(p[1] for p in ps) - min(p[1] for p in ps) >= 0.018, (
        "Lens is floating horizontally over the desktop"
    )
    assert min(p[0] for p in ps) > 7.77, "Lens must touch the curved rear board"


@pytest.mark.parametrize("module", [f"M{i:02d}" for i in range(1, 9)])
def test_every_bedroom_has_larger_lamps_and_enclosing_chair_backs(module):
    m = model("godot_project/rooms/estate/ElfieNest-complete-final.glb")
    for resident in "ABCD":
        nodes = [
            (i, n)
            for i, n in enumerate(m.doc["nodes"])
            if "mesh" in n
            and n.get("extras", {}).get("module") == module
            and n["extras"].get("resident") == resident
        ]
        globe = next(
            i
            for i, n in nodes
            if n["extras"].get("source_name") == "Desk | amber globe"
        )
        ps = list(mesh_points(m, globe))
        assert max(p[1] for p in ps) - min(p[1] for p in ps) > 0.18
        back = next(
            i
            for i, n in nodes
            if n["extras"].get("source_name") == "Chair | central tall back petal"
        )
        ps = list(mesh_points(m, back))
        assert max(p[1] for p in ps) - min(p[1] for p in ps) > 0.58


def test_room_crown_has_no_collapsed_clipping_faces():
    m = model("godot_project/rooms/estate/ElfieNest-complete-final.glb")
    node = next(
        i
        for i, n in enumerate(m.doc["nodes"])
        if n.get("extras", {}).get("module") == "M01"
        and n["extras"].get("source_name") == "ROOM • sculpted continuous shell"
        and "mesh" in n
    )
    for primitive in m.doc["meshes"][m.doc["nodes"][node]["mesh"]]["primitives"]:
        ps = _values(m, primitive["attributes"]["POSITION"])
        ix = [r[0] for r in _values(m, primitive["indices"])]
        for a, b, c in zip(ix[::3], ix[1::3], ix[2::3]):
            if max(ps[a][1], ps[b][1], ps[c][1]) < 3.099:
                continue
            u = [ps[b][k] - ps[a][k] for k in range(3)]
            v = [ps[c][k] - ps[a][k] for k in range(3)]
            cross = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            assert sum(x * x for x in cross) >= 4e-20


@pytest.mark.parametrize(
    "path",
    [
        "godot_project/rooms/estate/ElfieNest-complete-final.glb",
    ],
)
def test_second_floor_bookcase_diffuser_is_below_its_shelf(path):
    m = model(path)
    index = next(
        i
        for i, n in enumerate(m.doc["nodes"])
        if n.get("name") == "Draft L2 curved bookcase continuous hidden diffuser"
    )
    ps = list(mesh_points(m, index))
    assert max(p[1] for p in ps) < 4.701, (
        "Diffuser is buried inside the shelf instead of exposed beneath it"
    )


def test_m01_throw_uses_the_gap_between_the_right_hand_pillows():
    m = model("godot_project/rooms/estate/ElfieNest-complete-final.glb")
    sofa = next(
        i
        for i, n in enumerate(m.doc["nodes"])
        if n.get("name") == "sofa_following_actual_wall"
    )
    throw = next(
        i
        for i, n in enumerate(m.doc["nodes"])
        if n.get("name") == "linen_throw_on_fitted_sofa"
    )
    pillows = m.doc["meshes"][m.doc["nodes"][sofa]["mesh"]]["primitives"][2]
    ps = [p for p in _values(m, pillows["attributes"]["POSITION"]) if p[0] > 2.3]
    lower = max(p[2] for p in ps if p[2] < 0)
    upper = min(p[2] for p in ps if p[2] > 0)
    cloth = [
        p
        for pr in m.doc["meshes"][m.doc["nodes"][throw]["mesh"]]["primitives"]
        for p in _values(m, pr["attributes"]["POSITION"])
    ]
    assert min(p[2] for p in cloth) > lower + 0.05
    assert max(p[2] for p in cloth) < upper - 0.05
