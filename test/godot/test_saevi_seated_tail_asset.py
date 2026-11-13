"""Saevi tail authoring preserves geometry, body influences and bind-pose skinning."""

import collections
import hashlib
import json
import math
import os
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "godot_project/characters/saevi/saevi.glb"
EXPECTED = {
    "appearance": {
        "POSITION": "57945394486a64c25ee5972b4a8c546e00baa8ec58a140cdada3db314e38326a",
        "NORMAL": "190072e291e2f540cda82718d8c1e70d30fa4170b624eb48f791e321e225afff",
        "TEXCOORD_0": "8e1e5ca1576d5a9cd3ba882dc77922c9147754c5b1e6a52b9fa89b71ba78eea7",
        "body_texture": "0161296a1f1d4db88dc5f076ca5f63d02fb8de01d14803eaea561c2f9819b5d0",
        "materials": "ff8e3040c503e95bdde378bd818b96a2100112b36c3e5ade9dd0f6d346ce0ef1",
        "indices": "3c7109045721c54c0ca79edf60a4c09d21236adacddfa52b5433c0af127c2830",
    },
    "original_bind": "494f5cd24e020a467d858092c2df55801fb8177e569954cd03c70805482cbc04",
    "non_tail_weights": "14fb20c5c9db91fa0422460c2908a90ca57e10bccb6aafeef9d7a3f5f3846ead",
    "tail_region": "f0723586dc34ee64c4d9ec36ecaaea2091f1d889b74eb649be4ad139a0e2d847",
}


def read_asset():
    payload = Path(os.environ.get("SAEVI_TAIL_ASSET", ASSET)).read_bytes()
    size = struct.unpack_from("<I", payload, 12)[0]
    return json.loads(payload[20 : 20 + size]), payload[28 + size :]


def accessor(doc, binary, index):
    spec = doc["accessors"][index]
    view = doc["bufferViews"][spec["bufferView"]]
    kind = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[spec["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[spec["type"]]
    size = struct.calcsize(kind) * width
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    return [
        struct.unpack_from(
            "<" + kind * width, binary, start + i * view.get("byteStride", size)
        )
        for i in range(spec["count"])
    ]


def digest(value):
    return hashlib.sha256(value).hexdigest()


def emissive_pixels(doc, binary, primitive):
    material = doc["materials"][primitive["material"]]
    texture = doc["textures"][material["emissiveTexture"]["index"]]
    image = doc["images"][texture["source"]]
    view = doc["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    with Image.open(BytesIO(binary[start : start + view["byteLength"]])) as decoded:
        assert decoded.size == (2048, 2048)
        return digest(decoded.convert("RGBA").tobytes())


def appearance(doc, binary):
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    result = {}
    for name in ("POSITION", "NORMAL", "TEXCOORD_0"):
        result[name] = digest(
            b"".join(
                struct.pack("<" + "f" * len(v), *v)
                for v in accessor(doc, binary, attrs[name])
            )
        )
    primitive = doc["meshes"][0]["primitives"][0]
    material = doc["materials"][primitive["material"]]
    result["body_texture"] = emissive_pixels(doc, binary, primitive)
    result["materials"] = digest(json.dumps([material], sort_keys=True).encode())
    result["indices"] = digest(
        repr(accessor(doc, binary, primitive["indices"])).encode()
    )
    return result


def skin_rows(doc, binary):
    """Decode every paired influence set without assuming its slot placement."""
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    sets = sorted(int(k.split("_")[1]) for k in attrs if k.startswith("JOINTS_"))
    assert sets == sorted(
        int(k.split("_")[1]) for k in attrs if k.startswith("WEIGHTS_")
    )
    joints, weights = [], []
    for index in sets:
        js = accessor(doc, binary, attrs[f"JOINTS_{index}"])
        ws = accessor(doc, binary, attrs[f"WEIGHTS_{index}"])
        assert len(js) == len(ws) == doc["accessors"][attrs["POSITION"]]["count"]
        if not joints:
            joints = [() for _ in js]
            weights = [() for _ in ws]
        joints = [row + extra for row, extra in zip(joints, js)]
        weights = [row + extra for row, extra in zip(weights, ws)]
    return joints, weights


def tail_membership(doc, joints, weights):
    names = [doc["nodes"][index]["name"] for index in doc["skins"][0]["joints"]]
    return [
        any(names[j].startswith("Tail_") and w > 0 for j, w in zip(js, ws))
        for js, ws in zip(joints, weights)
    ]


def body_weights(doc, binary):
    skin = doc["skins"][0]
    joints, weights = skin_rows(doc, binary)
    tail = tail_membership(doc, joints, weights)
    rows = [
        sorted(
            (doc["nodes"][skin["joints"][j]]["name"], w)
            for j, w in zip(js, ws)
            if w > 0
        )
        for js, ws, is_tail in zip(joints, weights, tail)
        if not is_tail
    ]
    return digest(repr(rows).encode())


def multiply(a, b):
    return [
        sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
        for c in range(4)
        for r in range(4)
    ]


def world_matrices(doc):
    identity = [float(i % 5 == 0) for i in range(16)]
    parents = {
        child: i for i, n in enumerate(doc["nodes"]) for child in n.get("children", [])
    }
    cache = {}

    def world(index):
        if index in cache:
            return cache[index]
        node = doc["nodes"][index]
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        sx, sy, sz = node.get("scale", [1, 1, 1])
        tx, ty, tz = node.get("translation", [0, 0, 0])
        local = node.get(
            "matrix",
            [
                (1 - 2 * y * y - 2 * z * z) * sx,
                (2 * x * y + 2 * z * w) * sx,
                (2 * x * z - 2 * y * w) * sx,
                0,
                (2 * x * y - 2 * z * w) * sy,
                (1 - 2 * x * x - 2 * z * z) * sy,
                (2 * y * z + 2 * x * w) * sy,
                0,
                (2 * x * z + 2 * y * w) * sz,
                (2 * y * z - 2 * x * w) * sz,
                (1 - 2 * x * x - 2 * y * y) * sz,
                0,
                tx,
                ty,
                tz,
                1,
            ],
        )
        cache[index] = multiply(
            world(parents[index]) if index in parents else identity, local
        )
        return cache[index]

    return [world(i) for i in range(len(doc["nodes"]))]


def test_saevi_appearance_and_body_weights_unchanged():
    doc, binary = read_asset()
    assert appearance(doc, binary) == EXPECTED["appearance"]
    assert body_weights(doc, binary) == EXPECTED["non_tail_weights"]


def test_saevi_six_joint_skin_and_smooth_weights():
    doc, binary = read_asset()
    skin = doc["skins"][0]
    nodes = doc["nodes"]
    tail = [
        next((i for i, n in enumerate(nodes) if n["name"] == f"Tail_{j:02d}"), -1)
        for j in range(1, 7)
    ]
    assert -1 not in tail, "Saevi needs Tail_01..06 deform joints"
    assert all(i in skin["joints"] for i in tail)
    control = next(i for i, n in enumerate(nodes) if n["name"].endswith(":Tail_Bone"))
    for parent, child in zip([control] + tail, tail):
        assert child in nodes[parent]["children"]
    js, ws = skin_rows(doc, binary)
    binds = {skin["joints"].index(i) for i in tail}
    counts = [
        sum(j in binds and w > 0 for j, w in zip(jrow, wrow))
        for jrow, wrow in zip(js, ws)
    ]
    assert max(counts) == 4
    assert all(
        any(
            j == bind and w > 0
            for jrow, wrow in zip(js, ws)
            for j, w in zip(jrow, wrow)
        )
        for bind in binds
    )
    assert all(min(row) >= 0 and abs(sum(row) - 1) < 2e-6 for row in ws)
    assert body_weights(doc, binary) == EXPECTED["non_tail_weights"]


def test_saevi_default_rest_skinning_unchanged():
    doc, binary = read_asset()
    skin = doc["skins"][0]
    worlds = world_matrices(doc)
    inverses = accessor(doc, binary, skin["inverseBindMatrices"])
    # Every added joint must have the same neutral skin matrix as the old control.
    control = next(
        i for i, n in enumerate(doc["nodes"]) if n["name"].endswith(":Tail_Bone")
    )
    old = multiply(worlds[control], inverses[skin["joints"].index(control)])
    for index in skin["joints"]:
        if doc["nodes"][index]["name"].startswith("Tail_"):
            actual = multiply(worlds[index], inverses[skin["joints"].index(index)])
            assert max(abs(a - b) for a, b in zip(old, actual)) < 2e-5
    # Original joints, transforms and inverse binds are unchanged.
    original = [
        (doc["nodes"][i], inverses[j]) for j, i in enumerate(skin["joints"][:42])
    ]
    for node, _ in original:
        node.pop("children", None)
    assert digest(repr(original).encode()) == EXPECTED["original_bind"]
    assert math.isfinite(sum(old))
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    # The packed file drops the historical weight accessors. The frozen tail
    # vertex mask and body weights still identify every vertex independently.
    current_js, current_ws = skin_rows(doc, binary)
    tail = tail_membership(doc, current_js, current_ws)
    assert digest(bytes(tail)) == EXPECTED["tail_region"]
    assert body_weights(doc, binary) == EXPECTED["non_tail_weights"]
    tail_bind = skin["joints"].index(control)
    skin_matrices = [
        multiply(worlds[index], inverse)
        for index, inverse in zip(skin["joints"], inverses)
    ]
    positions = accessor(doc, binary, attrs["POSITION"])
    max_rest_error = 0.0
    for position, new_js, new_ws, is_tail in zip(
        positions, current_js, current_ws, tail
    ):
        if not is_tail:
            continue
        assert all(
            doc["nodes"][skin["joints"][j]]["name"].startswith("Tail_")
            for j, w in zip(new_js, new_ws)
            if w > 0
        )
        assert abs(sum(new_ws) - 1.0) < 2e-7

        def deform(joints, weights, position=position):
            return [
                sum(
                    w
                    * (
                        sum(skin_matrices[j][c * 4 + r] * position[c] for c in range(3))
                        + skin_matrices[j][12 + r]
                    )
                    for j, w in zip(joints, weights)
                )
                for r in range(3)
            ]

        original_position = deform((tail_bind,), (1.0,))
        new_position = deform(new_js, new_ws)
        max_rest_error = max(max_rest_error, math.dist(original_position, new_position))
    assert max_rest_error < 2e-6
    positions = accessor(doc, binary, attrs["POSITION"])
    old_inverse = inverses[tail_bind]
    local_y = [
        sum(old_inverse[c * 4 + 1] * p[c] for c in range(3)) + old_inverse[13]
        for p in positions
    ]
    accessor_tail_js = current_js
    tail_ws = [
        tuple(
            w if doc["nodes"][skin["joints"][j]]["name"].startswith("Tail_") else 0.0
            for j, w in zip(js, ws)
        )
        for js, ws in zip(current_js, current_ws)
    ]
    tail_nodes = [
        next(i for i, n in enumerate(doc["nodes"]) if n["name"] == f"Tail_{k:02d}")
        for k in range(1, 7)
    ]
    tail_vertices = [i for i, weights in enumerate(tail_ws) if sum(weights) > 0]
    low, high = (
        min(local_y[i] for i in tail_vertices),
        max(local_y[i] for i in tail_vertices),
    )
    for i in tail_vertices:
        u = max(0.0, min(1.0, (local_y[i] - low) / (high - low)))
        # Independent Cox-de Boor evaluation of the clamped cubic basis.
        knots = [0.0] * 4 + [1 / 3, 2 / 3] + [1.0] * 4

        def basis(k, degree, u=u, knots=knots):
            if degree == 0:
                return float(knots[k] <= u < knots[k + 1])
            left = knots[k + degree] - knots[k]
            right = knots[k + degree + 1] - knots[k + 1]
            return ((u - knots[k]) / left * basis(k, degree - 1) if left else 0) + (
                (knots[k + degree + 1] - u) / right * basis(k + 1, degree - 1)
                if right
                else 0
            )

        expected = [basis(k, 3) for k in range(6)] if u < 1 else [0, 0, 0, 0, 0, 1]
        extra_js = accessor_tail_js[i]
        actual = [
            sum(w for j, w in zip(extra_js, tail_ws[i]) if skin["joints"][j] == node)
            / sum(tail_ws[i])
            for node in tail_nodes
        ]
        assert max(abs(a - b) for a, b in zip(expected, actual)) < 1e-6
    first = min(tail_vertices, key=lambda i: local_y[i])
    assert sum(
        w
        for j, w in zip(accessor_tail_js[first], tail_ws[first])
        if skin["joints"][j] == tail_nodes[0]
    ) == sum(tail_ws[first])


def test_saevi_tail_region_is_one_surface_attached_only_at_narrow_root():
    doc, binary = read_asset()
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    positions = accessor(doc, binary, attrs["POSITION"])
    joints, weights = skin_rows(doc, binary)
    tail = tail_membership(doc, joints, weights)
    assert sum(tail) == 44606
    assert digest(bytes(tail)) == EXPECTED["tail_region"]
    # Exact-position welding removes UV seams without changing the source mesh.
    lookup, welded, vertices = {}, [], []
    for position in positions:
        if position not in lookup:
            lookup[position] = len(vertices)
            vertices.append(position)
        welded.append(lookup[position])
    labels = collections.defaultdict(set)
    for index, is_tail in zip(welded, tail):
        labels[index].add(is_tail)
    assert all(len(values) == 1 for values in labels.values())
    adjacent = [set() for _ in vertices]
    indices = [
        row[0]
        for row in accessor(doc, binary, doc["meshes"][0]["primitives"][0]["indices"])
    ]
    for i in range(0, len(indices), 3):
        a, b, c = [welded[k] for k in indices[i : i + 3]]
        for first, second in ((a, b), (b, c), (c, a)):
            adjacent[first].add(second)
            adjacent[second].add(first)
    boundary = [
        i
        for i, edges in enumerate(adjacent)
        if any(labels[i] != labels[j] for j in edges)
    ]
    assert len(boundary) == 94
    for i in boundary:
        x, y, z = vertices[i]
        assert -0.055371 <= x <= 0.056872
        assert 0.509290 <= y <= 0.622735
        assert 0.282904 <= z <= 0.309033
    # Both sides of the narrow attachment are connected: no hidden body islands
    # are selected, and no non-tail islands are left inside the rear appendage.
    for selected, expected_count in ((True, 20375), (False, 39621)):
        allowed = {i for i, values in labels.items() if selected in values}
        assert len(allowed) == expected_count
        pending = [allowed.pop()]
        while pending:
            for other in adjacent[pending.pop()]:
                if other in allowed:
                    allowed.remove(other)
                    pending.append(other)
        assert not allowed
    assert all(
        is_tail for position, is_tail in zip(positions, tail) if position[2] < 0.2
    )
