"""Flowers at both waterfall shoulders use complete existing flower assemblies."""

import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _runtime_groups():
    raw = (
        ROOT / "godot_project/nest/estate/ElfieNest-complete-final.instances.bin"
    ).read_bytes()
    magic, version, count, expected = struct.unpack_from("<8sIII", raw)
    assert magic == b"ENINST01" and version == 2
    offset = 20
    groups = {}
    seen = 0
    for _ in range(count):
        length, size = struct.unpack_from("<II", raw, offset)
        offset += 8
        name = raw[offset : offset + length].decode()
        offset += length
        rows = [struct.unpack_from("<12f", raw, offset + 48 * i) for i in range(size)]
        offset += 48 * size
        seen += size
        if name in {f"__ELFIE_INST_GROUP_{i:03d}" for i in range(91, 102)}:
            groups[name] = rows
    assert seen == expected and offset == len(raw)
    return groups


def _inside(point, side):
    x, _, z = point
    return 23.55 < x < 24.3 and (
        26.7 < z < 27.2 if side == "north" else 30.5 < z < 31.0
    )


def _position(row):
    return tuple(round(row[i], 4) for i in (3, 7, 11))


def _edge_x(z, side):
    # Surveyed landward edge of the existing shore light, in scene coordinates.
    edge = (
        [(25.85, 24.58), (26.25, 24.575), (26.75, 24.648), (27.25, 24.776)]
        if side == "north"
        else [(30.5, 24.784), (31.0, 24.534), (31.5, 24.218), (32.0, 23.887)]
    )
    for a, b in zip(edge, edge[1:]):
        if a[0] <= z <= b[0]:
            return a[1] + (b[1] - a[1]) * (z - a[0]) / (b[0] - a[0])
    return None


def _in_requested_strip(point, side):
    x, _, z = point
    edge = _edge_x(z, side)
    return edge is not None and 0.18 <= edge - x <= 0.60


@pytest.mark.parametrize("side", ["north", "south"])
def test_both_shoulders_have_complete_matching_flower_assemblies(side):
    groups = _runtime_groups()
    # Existing purple and pale-yellow flower parts: leaves, stems, petals and centers.
    for indices in (range(91, 95), range(98, 102)):
        positions = []
        for group in indices:
            runtime = {
                _position(row)
                for row in groups[f"__ELFIE_INST_GROUP_{group:03d}"]
                if _inside(_position(row), side)
            }
            positions.append(runtime)
        assert len(positions[0]) >= 2, (side, list(indices))
        assert any(point[0] >= 24.0 for point in positions[0]), (side, list(indices))
        assert all(group == positions[0] for group in positions[1:])


@pytest.mark.parametrize("side", ["north", "south"])
def test_flowers_fill_the_visible_lakeside_strip(side):
    groups = _runtime_groups()
    flowers = []
    for indices in (range(91, 95), range(98, 102)):
        parts = []
        for group in indices:
            runtime = {
                _position(row)
                for row in groups[f"__ELFIE_INST_GROUP_{group:03d}"]
                if _in_requested_strip(_position(row), side)
            }
            parts.append(runtime)
        assert all(part == parts[0] for part in parts[1:])
        assert len(parts[0]) >= 4, (side, list(indices))
        flowers.extend(parts[0])
    assert len(flowers) >= 12
    assert (
        max(point[2] for point in flowers) - min(point[2] for point in flowers) >= 1.0
    )
