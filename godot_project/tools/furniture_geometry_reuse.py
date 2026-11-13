"""Verify transform-only reuse of the approved V044 tabletop decorations."""

import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

from audit_shared_geometry import AUTHORING, ELEMENTS
from export_shared_asset_sources import read_document
from furniture_components import CUP_PLACEMENTS

MAX_POSITION_ERROR = 0.00001
MAX_NORMAL_ERROR = 0.0005
FORMATS = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}


def accessor(document, data, binary_start, index):
    item = document["accessors"][index]
    view = document["bufferViews"][item["bufferView"]]
    assert not item.get("sparse") and not item.get("normalized")
    row = struct.Struct("<" + FORMATS[item["componentType"]] * ELEMENTS[item["type"]])
    start = binary_start + view.get("byteOffset", 0) + item.get("byteOffset", 0)
    stride = view.get("byteStride", row.size)
    return [
        row.unpack_from(data, start + index * stride) for index in range(item["count"])
    ]


def rotate_xz(point, angle):
    x, y, z = point
    cosine, sine = math.cos(angle), math.sin(angle)
    return cosine * x - sine * z, y, sine * x + cosine * z


def align_book(positions, normals, indices):
    # V044 bakes the shelf's yaw and offsets into these horizontal book meshes.
    points = [positions[index] for index in indices]
    center = tuple(fmean(axis) for axis in zip(*points))
    xz = [(x - center[0], z - center[2]) for x, _, z in points]
    yaw = 0.5 * math.atan2(
        2 * math.fsum(x * z for x, z in xz), math.fsum(x * x - z * z for x, z in xz)
    )
    return (
        [rotate_xz(tuple(x - c for x, c in zip(p, center)), -yaw) for p in positions],
        [rotate_xz(n, -yaw) for n in normals],
        center,
        yaw,
    )


def align_radial(positions, normals, indices):
    center = tuple(fmean(axis) for axis in zip(*(positions[i] for i in indices)))
    yaw = math.atan2(center[2], center[0])
    return (
        [rotate_xz(tuple(x - c for x, c in zip(p, center)), -yaw) for p in positions],
        [rotate_xz(n, -yaw) for n in normals],
        center,
        yaw,
    )


def sample_mesh(record, documents, align):
    asset = record["asset"]
    if asset not in documents:
        data = (AUTHORING / f"{asset}.glb").read_bytes()
        document, binary_start = read_document(data)
        documents[asset] = document, data, binary_start
    document, data, binary_start = documents[asset]
    for primitive in document["meshes"][record["original_mesh"]]["primitives"]:
        assert primitive.get("mode", 4) == 4 and not primitive.get("targets")
        attrs = primitive["attributes"]
        positions = accessor(document, data, binary_start, attrs["POSITION"])
        normals = accessor(document, data, binary_start, attrs["NORMAL"])
        indices = [
            i for (i,) in accessor(document, data, binary_start, primitive["indices"])
        ]
        material = {
            key: value
            for key, value in document["materials"][primitive["material"]].items()
            if key != "name"
        }
        # UV and tangent rounding do not affect these constant-color materials.
        assert "Texture" not in str(material) and "COLOR_0" not in attrs
        if align:
            positions, normals, center, yaw = align(positions, normals, indices)
        else:
            center, yaw = (0.0, 0.0, 0.0), 0.0
        yield positions, normals, indices, material, center, yaw


def triangles(positions, indices):
    result = Counter()
    for offset in range(0, len(indices), 3):
        a, b, c = (positions[index] for index in indices[offset : offset + 3])
        result[min((a, b, c), (b, c, a), (c, a, b))] += 1
    return result


def measure_reuse(original, variant, documents, align):
    source = list(sample_mesh(original, documents, align))
    target = list(sample_mesh(variant, documents, align))
    assert source and len(source) == len(target) and (not align or len(source) == 1)
    position_error = normal_error = 0.0
    for source_part, target_part in zip(source, target):
        source_positions, source_normals, source_indices, source_material, _, _ = (
            source_part
        )
        positions, normals, indices, material, _, _ = target_part
        assert source_material == material and len(source_indices) == len(indices)
        points = set(source_positions)
        closest = {
            p: min(points, key=lambda q: math.dist(p, q)) for p in set(positions)
        }
        assert triangles(source_positions, source_indices) == triangles(
            [closest[p] for p in positions], indices
        )
        position_error = max(
            position_error, max(math.dist(p, q) for p, q in closest.items())
        )
        normals_at = defaultdict(list)
        for point, normal in zip(source_positions, source_normals):
            normals_at[point].append(normal)
        normal_error = max(
            normal_error,
            max(
                min(math.dist(n, other) for other in normals_at[closest[p]])
                for p, n in zip(positions, normals)
            ),
        )
    assert position_error < MAX_POSITION_ERROR and normal_error < MAX_NORMAL_ERROR
    source_center, source_yaw = source[0][-2:]
    center, yaw = target[0][-2:]
    yaw -= source_yaw
    return {
        "max_position_error_m": position_error,
        "max_normal_error": normal_error,
        "mesh_yaw_xz_radians": yaw,
        "mesh_translation": [
            x - y for x, y in zip(center, rotate_xz(source_center, yaw))
        ],
    }


def reuse_tabletop_geometry(plan, nodes):
    mesh_at = plan["mesh_at_path"]
    cups = {
        node["extras"]["central_furnishing"]: path
        for path, node in nodes.items()
        if node["extras"].get("central_furnishing") in CUP_PLACEMENTS
    }
    assert cups.keys() == set(CUP_PLACEMENTS)
    pairs = [(cups[CUP_PLACEMENTS[0]], cups[name], None) for name in CUP_PLACEMENTS[1:]]
    books = [
        path
        for path in mesh_at
        if Path(path).name.startswith("Botanical V1 front book ")
    ]
    assert len(books) == 9
    pairs.extend(
        (
            path,
            path.replace("Botanical V1 front book ", "Botanical V1 rear book "),
            align_book,
        )
        for path in books
    )
    return reuse_geometry(plan, pairs)


def reuse_courtyard_lamps(plan):
    fixture = "Generated/CompleteEstate/OutdoorLighting/Fixture_"
    return reuse_geometry(
        plan,
        [
            (f"{fixture}G1/{part}", f"{fixture}{target}/{part}", align_radial)
            for target in ("H01", "P05")
            for part in ("Diffuser", "SingleArmHousing")
        ],
    )


def reuse_geometry(plan, pairs):
    mesh_at = plan["mesh_at_path"]
    geometry = plan["geometry"]
    documents = {}
    aliases = {}
    for original, variant, align in pairs:
        shape, duplicate = mesh_at[original], mesh_at[variant]
        assert shape != duplicate and duplicate not in aliases
        aliases[duplicate] = {
            "geometry": shape,
            "source_path": original,
            "placement_path": variant,
            **measure_reuse(geometry[shape], geometry[duplicate], documents, align),
        }
    for path, shape in mesh_at.items():
        if shape in aliases:
            assert path == aliases[shape]["placement_path"], path
            mesh_at[path] = aliases[shape]["geometry"]
    for duplicate in aliases:
        del geometry[duplicate]
    return aliases
