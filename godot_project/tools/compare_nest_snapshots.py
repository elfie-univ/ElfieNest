"""Compare evaluated Nest worlds without cameras or sampling away differences.

For corresponding triangles the maximum displacement at their vertices bounds
the displacement of every point on those triangles (by barycentric convexity).
This is an upper bound, not an estimated or exact Hausdorff distance. Topology
without a verified correspondence stays unresolved and cannot pass.
"""

import argparse
import hashlib
import itertools
import json
import math
import mmap
import struct
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALGORITHM_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def triangle_multiset(points, indices):
    """Canonical cyclic corner order; retain winding and repeated triangles."""
    if len(indices) % 3:
        raise ValueError("Triangle index count is not divisible by three")
    result = Counter()
    for offset in range(0, len(indices), 3):
        a, b, c = (tuple(points[indices[offset + k]]) for k in range(3))
        result[min((a, b, c), (b, c, a), (c, a, b))] += 1
    return result


def vertex_correspondence(before, after):
    a, b = before["position"], after["position"]
    if len(a) != len(b):
        return None
    positions = defaultdict(list)
    for index, point in enumerate(b):
        positions[tuple(point)].append(index)
    mapping = []
    for point in a:
        candidates = positions.get(tuple(point))
        if not candidates:
            return None
        mapping.append(candidates.pop())
    if triangle_multiset(a, before["index"]) != triangle_multiset(b, after["index"]):
        return None
    return mapping


def maximum_displacement(before, after):
    if len(before) != len(after):
        raise ValueError("Different vertex counts")
    return max((math.dist(a, b) for a, b in zip(before, after)), default=0.0)


def semantic_value(value):
    if isinstance(value, dict):
        if {"dtype", "sha256", "offset", "bytes", "count"} <= value.keys():
            return {key: value[key] for key in ("dtype", "sha256", "bytes", "count")}
        return {
            key: semantic_value(item) for key, item in value.items() if key != "source"
        }
    if isinstance(value, list):
        return [semantic_value(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def match_placements(before, after, radius=0.05):
    """Match occurrences, never sets of positions. Radius is NOT a pass tolerance."""
    by_path = defaultdict(list)
    by_cell = defaultdict(list)

    def cell(center):
        return tuple(math.floor(value / radius) for value in center)

    for index, item in enumerate(after):
        by_path[item["kind"], item["path"]].append(index)
        by_cell[item["kind"], cell(item["center"])].append(index)
    used, pairs, pending = set(), [], []
    for index, item in enumerate(before):
        options = [j for j in by_path[item["kind"], item["path"]] if j not in used]
        if not options:
            pending.append(index)
            continue
        chosen = min(
            options, key=lambda j: (math.dist(item["center"], after[j]["center"]), j)
        )
        pairs.append((index, chosen))
        used.add(chosen)
    missing = []
    for index in pending:
        item = before[index]
        at = cell(item["center"])
        options = [
            j
            for delta in itertools.product((-1, 0, 1), repeat=3)
            for j in by_cell[item["kind"], tuple(a + b for a, b in zip(at, delta))]
            if j not in used and math.dist(item["center"], after[j]["center"]) <= radius
        ]
        if not options:
            missing.append(index)
            continue
        chosen = min(
            options, key=lambda j: (math.dist(item["center"], after[j]["center"]), j)
        )
        used.add(chosen)
        pairs.append((index, chosen))
    return sorted(pairs), missing, sorted(set(range(len(after))) - used)


def point(matrix, value):
    x, y, z = value
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def multiply(a, b):
    return tuple(
        sum(a[4 * k + r] * b[4 * c + k] for k in range(4))
        for c in range(4)
        for r in range(4)
    )


def normal_matrix(matrix):
    a, b, c = (matrix[:3], matrix[4:7], matrix[8:11])

    def cross(x, y):
        return (
            x[1] * y[2] - x[2] * y[1],
            x[2] * y[0] - x[0] * y[2],
            x[0] * y[1] - x[1] * y[0],
        )

    x, y, z = cross(b, c), cross(c, a), cross(a, b)
    determinant = sum(i * j for i, j in zip(a, x))
    if abs(determinant) < 1e-20:
        raise ValueError("Singular instance transform")
    return tuple(
        component / determinant for column in (x, y, z) for component in column
    )


def direction(matrix, vector):
    x, y, z = vector
    a = matrix[0] * x + matrix[3] * y + matrix[6] * z
    b = matrix[1] * x + matrix[4] * y + matrix[7] * z
    c = matrix[2] * x + matrix[5] * y + matrix[8] * z
    length = math.hypot(a, b, c)
    return (a / length, b / length, c / length) if length else (a, b, c)


def determinant_sign(matrix):
    return (
        1
        if (
            matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9])
            - matrix[4] * (matrix[1] * matrix[10] - matrix[2] * matrix[9])
            + matrix[8] * (matrix[1] * matrix[6] - matrix[2] * matrix[5])
        )
        > 0
        else -1
    )


class Rows:
    FORMATS = {
        "u8": ("B", 1),
        "i32": ("i", 1),
        "i64": ("q", 1),
        "f64": ("d", 1),
        "f32": ("f", 1),
        "v2f32": ("f", 2),
        "v3f32": ("f", 3),
        "v4f32": ("f", 4),
    }

    def __init__(self, data, description):
        self.data, self.description = data, description
        kind, self.width = self.FORMATS[description["dtype"]]
        self.row = struct.Struct("<" + kind * self.width)
        self.count = description["count"]
        if description["bytes"] != self.row.size * self.count:
            raise ValueError("Invalid array byte count")
        if description["offset"] < 0 or description["offset"] + description[
            "bytes"
        ] > len(data):
            raise ValueError("Snapshot array outside buffer")

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if index < 0 or index >= self.count:
            raise IndexError(index)
        values = self.row.unpack_from(
            self.data, self.description["offset"] + index * self.row.size
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Nonfinite snapshot coordinate")
        return values[0] if self.width == 1 else values

    def components(self, index, width):
        if (index + 1) * width > self.count:
            raise ValueError("Truncated flattened vertex attribute")
        kind = self.FORMATS[self.description["dtype"]][0]
        values = struct.unpack_from(
            "<" + kind * width,
            self.data,
            self.description["offset"] + index * width * self.row.size,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Nonfinite vertex attribute")
        return values


class Snapshot:
    def __init__(self, path):
        self.path = Path(path)
        self.document = json.loads(self.path.read_text())
        if self.document.get("schema") != 1:
            raise ValueError("Unsupported snapshot schema")
        self.stream = self.path.with_suffix(".bin").open("rb")
        self.data = mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_READ)
        if hashlib.sha256(self.data).hexdigest() != self.document["buffer_sha256"]:
            raise ValueError("Snapshot binary hash mismatch")
        self.resources, self.resolving = {}, set()

    def close(self):
        self.data.close()
        self.stream.close()

    def rows(self, description):
        return Rows(self.data, description)

    def resolve(self, value):
        if isinstance(value, dict) and set(value) == {"resource"}:
            key = value["resource"]
            if key in self.resolving:
                raise ValueError("Cyclic render resource")
            if key not in self.resources:
                self.resolving.add(key)
                self.resources[key] = self.resolve(self.document["resources"][key])
                self.resolving.remove(key)
            return self.resources[key]
        if isinstance(value, dict):
            if "type" in value and isinstance(value.get("mesh"), str):
                value = {**value, "mesh": self.document["meshes"][value["mesh"]]}
            if value.get("type") == "StandardMaterial3D":
                raw = value["properties"]
                properties = {key: self.resolve(item) for key, item in raw.items()}
                # Godot 4.7's Compatibility shader reconstructs normal Z from XY.
                # ORM textures consume their selected channel, not every byte of
                # an exporter's repacked image. Custom shaders retain full RGBA.
                for key, channels in {
                    "normal_texture": (0, 1),
                    **{
                        name + "_texture": (raw.get(name + "_texture_channel", 0),)
                        for name in ("metallic", "roughness", "ao")
                    },
                }.items():
                    if raw.get(key) is not None:
                        properties[key] = self.texture_channels(raw[key], channels)
                return {"type": value["type"], "properties": properties}
            return semantic_value(
                {
                    key: self.resolve(item)
                    for key, item in value.items()
                    if key != "source"
                }
            )
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def texture_channels(self, reference, channels):
        raw = self.document["resources"][reference["resource"]]
        image = raw.get("image", {})
        if (
            raw.get("type") != "Texture2D"
            or image.get("format") != 5
            or any(c > 3 for c in channels)
        ):
            return self.resolve(reference)
        key = (reference["resource"], channels)
        if key not in self.resources:
            desc = image["pixels"]
            Rows(self.data, desc)  # Validate byte range before taking the view.
            data = self.data[desc["offset"] : desc["offset"] + desc["bytes"]]
            hashes = [hashlib.sha256(data[c::4]).hexdigest() for c in channels]
            self.resources[key] = {
                "type": "Texture2D",
                "image": {
                    **{k: v for k, v in image.items() if k != "pixels"},
                    "channels": channels,
                    "channel_sha256": hashes,
                },
            }
        return self.resources[key]


def surface_data(snapshot, surface):
    arrays = {key: snapshot.rows(value) for key, value in surface["arrays"].items()}
    if "position" not in arrays:
        raise ValueError("Mesh surface without vertices")
    if "index" not in arrays:
        arrays["index"] = range(len(arrays["position"]))
    return arrays


def attribute_row(rows, index, width):
    if isinstance(rows, Rows) and rows.width == 1 and width > 1:
        return rows.components(index, width)
    return (
        rows[index]
        if rows.width > 1 or width == 1
        else tuple(rows[index * width + k] for k in range(width))
    )


def triangle_correspondence(a, b, ma, mb, radius=0.0001):
    """Pair every oriented triangle, allowing reordered/split corner vertices.

    The radius only finds candidate correspondences. Actual displacement is
    measured afterwards, without rounding it to this radius or calling it zero.
    """
    if len(a["index"]) != len(b["index"]) or len(a["index"]) % 3:
        return None
    if ma == mb:
        relative = IDENTITY
    else:
        normal = normal_matrix(ma)
        inverse = [0.0] * 16
        inverse[15] = 1.0
        for column in range(3):
            for row in range(3):
                inverse[column * 4 + row] = normal[row * 3 + column]
        for row in range(3):
            inverse[12 + row] = -sum(
                inverse[4 * column + row] * ma[12 + column] for column in range(3)
            )
        relative = multiply(inverse, mb)
    target_points = [point(relative, item) for item in b["position"]]
    locations = set(target_points)
    cells = defaultdict(list)
    for item in locations:
        cells[tuple(math.floor(x / radius) for x in item)].append(item)
    labels = [None] * len(a["position"])
    for index in set(a["index"]):
        raw = a["position"][index]
        item = tuple(raw)
        if item in locations:
            labels[index] = item
            continue
        at = tuple(math.floor(x / radius) for x in item)
        candidates = [
            q
            for delta in itertools.product((-1, 0, 1), repeat=3)
            for q in cells[tuple(x + y for x, y in zip(at, delta))]
            if math.dist(item, q) <= radius
        ]
        if not candidates:
            return None
        labels[index] = min(candidates, key=lambda q: (math.dist(item, q), q))

    def canonical(points, indices):
        rotations = [tuple(indices[k:] + indices[:k]) for k in range(3)]
        ordered = min(rotations, key=lambda order: tuple(points[i] for i in order))
        return tuple(points[i] for i in ordered), ordered

    triangles = defaultdict(list)
    for at in range(0, len(b["index"]), 3):
        key, order = canonical(target_points, [b["index"][at + k] for k in range(3)])
        triangles[key].append(order)
    normals_a, normals_b = normal_matrix(ma), normal_matrix(mb)
    corner_cache = {}

    def corner(side, index):
        key = side, index
        if key not in corner_cache:
            arrays, matrix = (a, normals_a) if side == 0 else (b, normals_b)
            normal = (
                direction(matrix, arrays["normal"][index]) if "normal" in arrays else ()
            )
            other = tuple(
                v
                for name, width in (("uv", 2), ("uv2", 2), ("color", 4))
                if name in arrays
                for v in attribute_row(arrays[name], index, width)
            )
            if "tangent" in arrays:
                basis = ma if side == 0 else mb
                raw = attribute_row(arrays["tangent"], index, 4)
                tangent_matrix = tuple(basis[k] for k in (0, 1, 2, 4, 5, 6, 8, 9, 10))
                other += (
                    *direction(tangent_matrix, raw[:3]),
                    raw[3] * determinant_sign(basis),
                )
            corner_cache[key] = normal, other
        return corner_cache[key]

    def score(order, target):
        normal = other = 0.0
        for source_index, target_index in zip(order, target):
            x, y = corner(0, source_index), corner(1, target_index)
            normal += sum((p - q) ** 2 for p, q in zip(x[0], y[0]))
            other += sum((p - q) ** 2 for p, q in zip(x[1], y[1]))
        return normal + other, normal, other

    pairs = set()
    for at in range(0, len(a["index"]), 3):
        key, order = canonical(labels, [a["index"][at + k] for k in range(3)])
        candidates = triangles.get(key)
        if not candidates:
            return None
        if len(candidates) > 1 or len(set(key)) < 3:
            options = [
                (score(order, rotation), index, rotation)
                for index, candidate in enumerate(candidates)
                for k in range(3)
                for rotation in [candidate[k:] + candidate[:k]]
                if tuple(target_points[i] for i in rotation) == key
            ]
            _, chosen, target = min(options)
            candidates.pop(chosen)
        else:
            target = candidates.pop()
        pairs.update(zip(order, target))
    if any(triangles.values()):
        return None
    return sorted(pairs)


def compare_surface(left, right, old, new, matrix_a, matrix_b, correspondences=None):
    result = {
        "max_position_m": 0.0,
        "max_normal_degrees": 0.0,
        "attributes": {},
        "corresponding": False,
    }
    if old["primitive"] != 3 or new["primitive"] != 3:
        result["unresolved"] = (
            "Only triangle surfaces have a whole-surface displacement proof"
        )
        return result
    a, b = surface_data(left, old), surface_data(right, new)
    same_positions = (
        old["arrays"]["position"]["sha256"] == new["arrays"]["position"]["sha256"]
    )
    same_indices = len(a["index"]) == len(b["index"]) and all(
        x == y for x, y in zip(a["index"], b["index"])
    )
    same_count = len(a["position"]) == len(b["position"])
    cache_key = tuple(
        tuple(
            (name, value["sha256"]) for name, value in sorted(surface["arrays"].items())
        )
        for surface in (old, new)
    )
    identical_arrays = all(
        semantic_value(old["arrays"].get(name))
        == semantic_value(new["arrays"].get(name))
        for name in set(old["arrays"]) | set(new["arrays"])
    )
    if (
        same_positions
        and same_indices
        and same_count
        and identical_arrays
        and matrix_a == matrix_b
    ):
        pairs = [(i, i) for i in range(len(a["position"]))]
    elif correspondences is not None and cache_key in correspondences:
        pairs = correspondences[cache_key]
    else:
        pairs = triangle_correspondence(a, b, matrix_a, matrix_b)
        if pairs is None and same_indices and same_count:
            pairs = [(i, i) for i in range(len(a["position"]))]
        if pairs is not None and correspondences is not None:
            # This bijection of triangle corners remains valid under any pose.
            # Only topology is reused; each instance's error is remeasured.
            correspondences[cache_key] = pairs
    if pairs is None:
        result["unresolved"] = "No verified oriented triangle/vertex correspondence"
        return result
    result["corresponding"] = True
    if not (same_positions and matrix_a == matrix_b):
        maximum = 0.0
        literal_equal = True
        for index, target in pairs:
            p, q = a["position"][index], b["position"][target]
            if matrix_a == matrix_b and p == q:
                continue
            literal_equal = False
            # Subtract the common origin before transforming. Subtracting two
            # large absolute world coordinates can erase a real small change.
            delta = tuple(
                math.fsum(
                    [matrix_a[4 * k + r] * (p[k] - q[k]) for k in range(3)]
                    + [
                        (matrix_a[4 * k + r] - matrix_b[4 * k + r]) * q[k]
                        for k in range(3)
                    ]
                    + [matrix_a[12 + r] - matrix_b[12 + r]]
                )
                for r in range(3)
            )
            maximum = max(
                maximum,
                math.hypot(*delta),
            )
        result["max_position_m"] = maximum
        if maximum == 0 and not literal_equal:
            ma, mb = [Fraction(v) for v in matrix_a], [Fraction(v) for v in matrix_b]
            for index, target in pairs:
                p, q = (
                    [Fraction(v) for v in a["position"][index]],
                    [Fraction(v) for v in b["position"][target]],
                )
                if any(
                    sum(ma[4 * k + r] * p[k] - mb[4 * k + r] * q[k] for k in range(3))
                    + ma[12 + r]
                    - mb[12 + r]
                    for r in range(3)
                ):
                    result["unresolved"] = (
                        "Position difference below floating arithmetic resolution"
                    )
                    break
    widths = {"normal": 3, "tangent": 4, "color": 4, "uv": 2, "uv2": 2}
    for name in (set(a) | set(b)) - {"position", "index"}:
        if name not in a or name not in b:
            result["attributes"][name] = "attribute added or removed"
            continue
        same = semantic_value(old["arrays"][name]) == semantic_value(
            new["arrays"][name]
        )
        basis_same = tuple(matrix_a[:12]) == tuple(matrix_b[:12])
        unchanged_order = all(index == target for index, target in pairs)
        if (
            same
            and unchanged_order
            and (name not in {"normal", "tangent"} or basis_same)
        ):
            continue
        if name not in widths:
            result["attributes"][name] = "binary data differs"
            continue
        if name == "normal":
            na, nb = normal_matrix(matrix_a), normal_matrix(matrix_b)
            worst = length_delta = 0.0
            for index, target in pairs:
                raw_a, raw_b = a[name][index], b[name][target]
                length_delta = max(
                    length_delta,
                    abs(math.hypot(*raw_a) - math.hypot(*raw_b)),
                )
                x, y = direction(na, raw_a), direction(nb, raw_b)
                if x == y:
                    continue
                cosine = max(-1.0, min(1.0, sum(p * q for p, q in zip(x, y))))
                worst = max(worst, math.degrees(math.acos(cosine)))
            result["max_normal_degrees"] = worst
            if worst:
                result["attributes"][name] = worst
            if length_delta:
                result["attributes"]["normal_length"] = length_delta
        elif name == "tangent":
            ta = tuple(matrix_a[k] for k in (0, 1, 2, 4, 5, 6, 8, 9, 10))
            tb = tuple(matrix_b[k] for k in (0, 1, 2, 4, 5, 6, 8, 9, 10))
            worst = 0.0
            handedness = 0
            sign_a, sign_b = determinant_sign(matrix_a), determinant_sign(matrix_b)
            for index, target in pairs:
                raw_a, raw_b = (
                    attribute_row(a[name], index, 4),
                    attribute_row(b[name], target, 4),
                )
                x, y = direction(ta, raw_a[:3]), direction(tb, raw_b[:3])
                if x != y:
                    worst = max(
                        worst,
                        math.degrees(
                            math.acos(
                                max(-1.0, min(1.0, sum(p * q for p, q in zip(x, y))))
                            )
                        ),
                    )
                handedness += raw_a[3] * sign_a != raw_b[3] * sign_b
            if worst or handedness:
                result["attributes"][name] = {
                    "angle_degrees": worst,
                    "handedness_differences": handedness,
                }
        else:
            width = widths[name]
            maximum = 0.0
            for index, target in pairs:
                x, y = (
                    attribute_row(a[name], index, width),
                    attribute_row(b[name], target, width),
                )
                maximum = max(maximum, max(abs(p - q) for p, q in zip(x, y)))
            if maximum:
                result["attributes"][name] = maximum
    return result


def batch_bound(local, matrices, targets=None, bounds=None):
    """Bound every identical-buffer instance, including nonuniform transforms.

    ||A||_2 <= ||A||_F bounds position error. For normalized normals/tangents,
    tan(theta_world/2) <= cond(A) * tan(theta_local/2); the Frobenius condition
    bound is conservative. Zero error remains zero without numeric sampling.
    """
    position_error = normal_error = tangent_error = 0.0
    paired = ((m, m) for m in matrices) if targets is None else zip(matrices, targets)
    local_tangent = max(
        (
            v.get("attributes", {}).get("tangent", {}).get("angle_degrees", 0)
            for v in local.get("surfaces", [])
        ),
        default=0,
    )

    def angle(value, condition):
        return math.degrees(
            2 * math.atan(condition * math.tan(math.radians(min(value, 180)) / 2))
        )

    for ma, mb in paired:
        basis_a = [ma[k] for k in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
        basis_b = [mb[k] for k in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
        na, nb = normal_matrix(ma), normal_matrix(mb)
        norm = math.sqrt(sum(v * v for v in basis_b))
        inverse = math.sqrt(sum(v * v for v in nb))
        condition = norm * inverse
        transform_error = normal_rotation = tangent_rotation = 0.0
        if ma != mb:
            if bounds is None:
                raise ValueError("Changed batch transforms require exact vertex bounds")
            delta = tuple(x - y for x, y in zip(ma, mb))
            transform_error = max(
                math.sqrt(sum(v * v for v in point(delta, corner)))
                for corner in itertools.product(*zip(*bounds))
            )
            normal_delta = math.sqrt(sum((x - y) ** 2 for x, y in zip(na, nb)))
            normal_rotation = math.degrees(2 * math.asin(min(1, normal_delta * norm)))
            tangent_delta = math.sqrt(
                sum((x - y) ** 2 for x, y in zip(basis_a, basis_b))
            )
            tangent_rotation = math.degrees(
                2 * math.asin(min(1, tangent_delta * inverse))
            )
        position_error = max(
            position_error, transform_error + local.get("position", 0) * norm
        )
        normal_error = max(
            normal_error,
            min(180, normal_rotation + angle(local.get("normal", 0), condition)),
        )
        tangent_error = max(
            tangent_error, min(180, tangent_rotation + angle(local_tangent, condition))
        )

    return {
        **local,
        "position": position_error,
        "normal": normal_error,
        "bound": "All instance matrices; Frobenius position/normal upper bounds",
        "max_tangent_upper_bound_degrees": tangent_error,
    }


def field_differences(a, b, prefix=""):
    """Keep reports reviewable without losing any differing field."""
    if a == b:
        return []
    if isinstance(a, dict) and isinstance(b, dict):
        return [
            item
            for key in sorted(set(a) | set(b))
            for item in field_differences(
                a.get(key), b.get(key), prefix + "/" + str(key)
            )
        ]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [
            item
            for i, (x, y) in enumerate(zip(a, b))
            for item in field_differences(x, y, prefix + "/" + str(i))
        ]
    return [{"field": prefix, "reference": a, "reassembled": b}]


def batch_rows(snapshot, placement):
    batch = placement["batch"]
    if batch["format"] != 1:
        raise ValueError("A Nest instance batch must use 3D transforms")
    rows = snapshot.rows(batch["buffer"])
    stride = 12 + 4 * batch["colors"] + 4 * batch["custom_data"]
    if len(rows) != batch["count"] * stride:
        raise ValueError("Truncated MultiMesh instance buffer")
    for index in range(batch["count"]):
        values = tuple(rows[index * stride + k] for k in range(stride))
        matrix = (
            values[0],
            values[4],
            values[8],
            0,
            values[1],
            values[5],
            values[9],
            0,
            values[2],
            values[6],
            values[10],
            0,
            values[3],
            values[7],
            values[11],
            1,
        )
        yield multiply(placement["matrix"], matrix), values[12:]


def compare(reference, reassembled):
    a, b = reference.document, reassembled.document
    pairs, missing, extra = match_placements(a["placements"], b["placements"])
    report = {
        "schema": 1,
        "method": "whole-world triangle correspondence; per-vertex maximum is a whole-surface upper bound",
        "snapshots": {
            "reference": str(reference.path),
            "reassembled": str(reassembled.path),
        },
        "coverage": {
            "reference_placements": len(a["placements"]),
            "reassembled_placements": len(b["placements"]),
            "matched": len(pairs),
            "instances": 0,
            "surface_comparisons": 0,
            "triangle_occurrences": 0,
            "verified_triangle_occurrences": 0,
        },
        "missing": [a["placements"][i] for i in missing],
        "extra": [b["placements"][i] for i in extra],
        "differences": [],
        "unresolved": [],
        "max_position_m": 0.0,
        "max_normal_degrees": 0.0,
        "export_errors": a["errors"] + b["errors"],
    }
    cache, correspondences = {}, {}

    def geometry(old, new, ma, mb):
        old_mesh, new_mesh = a["meshes"][old["mesh"]], b["meshes"][new["mesh"]]
        key = (
            old["mesh"],
            new["mesh"],
            tuple(ma[:12]),
            tuple(mb[:12]),
            tuple(x - y for x, y in zip(ma[12:15], mb[12:15])),
        )
        if key in cache:
            return cache[key]
        if (
            len(old_mesh["surfaces"]) != len(new_mesh["surfaces"])
            or old_mesh["blend_shapes"]
            or new_mesh["blend_shapes"]
        ):
            result = {"unresolved": "Surface count mismatch or unhandled blend shapes"}
        else:
            values = [
                compare_surface(reference, reassembled, x, y, ma, mb, correspondences)
                for x, y in zip(old_mesh["surfaces"], new_mesh["surfaces"])
            ]
            report["coverage"]["surface_comparisons"] += len(values)
            result = {
                "position": max((v["max_position_m"] for v in values), default=0.0),
                "normal": max((v["max_normal_degrees"] for v in values), default=0.0),
                "surfaces": values,
            }
            if any(not v["corresponding"] or "unresolved" in v for v in values):
                result["unresolved"] = "Unmatched surface topology"
        cache[key] = result
        return result

    for number, (i, j) in enumerate(pairs):
        old, new = a["placements"][i], b["placements"][j]
        issues = {}
        result = {}
        if old["kind"] == "batch":
            x, y = old["batch"], new["batch"]
            report["coverage"]["instances"] += x["count"]
            invalid_buffer = any(
                batch["buffer"]["count"]
                != batch["count"]
                * (12 + 4 * batch["colors"] + 4 * batch["custom_data"])
                for batch in (x, y)
            )
            if invalid_buffer:
                issues["batch"] = "Missing or truncated instance buffer"
                result["unresolved"] = issues["batch"]
            elif {
                k: x[k] for k in ("count", "visible", "colors", "custom_data", "format")
            } != {
                k: y[k] for k in ("count", "visible", "colors", "custom_data", "format")
            }:
                issues["batch"] = "Instance count, visibility or channel layout differs"
                result["unresolved"] = issues["batch"]
            else:
                same_buffer = x["buffer"]["sha256"] == y["buffer"]["sha256"]
                if same_buffer:
                    local = geometry(old, new, IDENTITY, IDENTITY)
                    positions = [
                        vertex
                        for surface in a["meshes"][old["mesh"]]["surfaces"]
                        for vertex in surface_data(reference, surface)["position"]
                    ]
                    bounds = [
                        tuple(min(v[k] for v in positions) for k in range(3)),
                        tuple(max(v[k] for v in positions) for k in range(3)),
                    ]
                    result = batch_bound(
                        local,
                        (matrix for matrix, _ in batch_rows(reference, old)),
                        (matrix for matrix, _ in batch_rows(reassembled, new)),
                        bounds,
                    )
                else:
                    worst_position = worst_normal = 0.0
                    channel_differences = 0
                    unresolved = False
                    surface_issues = {}
                    for (ma, ca), (mb, cb) in zip(
                        batch_rows(reference, old), batch_rows(reassembled, new)
                    ):
                        item = geometry(old, new, ma, mb)
                        worst_position = max(worst_position, item.get("position", 0.0))
                        worst_normal = max(worst_normal, item.get("normal", 0.0))
                        channel_differences += ca != cb
                        unresolved = unresolved or "unresolved" in item
                        for surface in item.get("surfaces", []):
                            if surface.get("attributes"):
                                surface_issues[digest(surface["attributes"])] = surface[
                                    "attributes"
                                ]
                    result = {
                        "position": worst_position,
                        "normal": worst_normal,
                        "surface_attribute_differences": list(surface_issues.values()),
                    }
                    if unresolved:
                        result["unresolved"] = "Unmatched batch-instance topology"
                    if channel_differences:
                        issues["instance_channels"] = channel_differences
        else:
            result = geometry(old, new, old["matrix"], new["matrix"])
        triangles = sum(
            surface["arrays"].get("index", surface["arrays"]["position"])["count"] // 3
            for surface in a["meshes"][old["mesh"]]["surfaces"]
        )
        triangles *= old.get("batch", {}).get("count", 1)
        report["coverage"]["triangle_occurrences"] += triangles
        if "unresolved" not in result:
            report["coverage"]["verified_triangle_occurrences"] += triangles
        if "unresolved" in result:
            report["unresolved"].append(
                {
                    "path": old["path"],
                    "file": new["file"],
                    "reason": result["unresolved"],
                }
            )
        report["max_position_m"] = max(
            report["max_position_m"], result.get("position", 0.0)
        )
        report["max_normal_degrees"] = max(
            report["max_normal_degrees"], result.get("normal", 0.0)
        )
        if (
            result.get("position")
            or result.get("normal")
            or result.get("surface_attribute_differences")
            or any(v.get("attributes") for v in result.get("surfaces", []))
        ):
            issues["geometry"] = result
        for field in ("materials", "overlay", "draw", "visible"):
            if reference.resolve(old.get(field)) != reassembled.resolve(new.get(field)):
                issues[field] = field_differences(
                    reference.resolve(old.get(field)),
                    reassembled.resolve(new.get(field)),
                )
        if issues:
            report["differences"].append(
                {
                    "path": old["path"],
                    "file": new["file"],
                    "node": new["node"],
                    "issues": issues,
                }
            )
        if number % 100 == 0:
            print(f"Compared {number}/{len(pairs)} placements", flush=True)
    for category in ("lights", "particles"):
        source, target = a[category], b[category]
        matched, lost, added = match_placements(source, target)
        changes = []
        for i, j in matched:
            x, y = source[i], target[j]
            different = [
                key
                for key in ("matrix", "visible", "state")
                if reference.resolve(x.get(key)) != reassembled.resolve(y.get(key))
            ]
            if different:
                changes.append(
                    {
                        "path": x["path"],
                        "differences": {
                            key: field_differences(
                                reference.resolve(x.get(key)),
                                reassembled.resolve(y.get(key)),
                            )
                            for key in different
                        },
                    }
                )
        report[category] = {
            "reference": len(source),
            "reassembled": len(target),
            "missing": lost,
            "extra": added,
            "differences": changes,
        }
    report["environment_equal"] = reference.resolve(
        a["environments"]
    ) == reassembled.resolve(b["environments"])
    report["max_normal_degrees_is_upper_bound"] = True
    report["max_position_m_is_upper_bound"] = True
    report["state_equal"] = a["state"] == b["state"] and a["engine"] == b["engine"]
    report["algorithm_sha256"] = ALGORITHM_SHA256
    report["strictly_equal"] = (
        not any(
            report[key]
            for key in (
                "missing",
                "extra",
                "differences",
                "unresolved",
                "export_errors",
            )
        )
        and report["environment_equal"]
        and all(
            not report[k][f]
            for k in ("lights", "particles")
            for f in ("missing", "extra", "differences")
        )
    )
    report["strictly_equal"] = report["strictly_equal"] and report["state_equal"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference", type=Path, default=ROOT / "build/nest-comparison/reference.json"
    )
    parser.add_argument(
        "--reassembled",
        type=Path,
        default=ROOT / "build/nest-comparison/reassembled.json",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build/nest-comparison/comparison.json"
    )
    args = parser.parse_args()
    source, target = Snapshot(args.reference), Snapshot(args.reassembled)
    try:
        report = compare(source, target)
        report["input_sha256"] = source.document["inputs"]
        report["stale_inputs"] = [
            name
            for name, expected in source.document["inputs"].items()
            if not name.startswith("res://")
            or not (ROOT / "godot_project" / name.removeprefix("res://")).is_file()
            or hashlib.sha256(
                (ROOT / "godot_project" / name.removeprefix("res://")).read_bytes()
            ).hexdigest()
            != expected
        ]
        report["input_sets_equal"] = (
            source.document["inputs"] == target.document["inputs"]
        )
        report["snapshot_sha256"] = {
            str(item.path): hashlib.sha256(item.path.read_bytes()).hexdigest()
            for item in (source, target)
        }
        report["strictly_equal"] = (
            report["strictly_equal"]
            and not report["stale_inputs"]
            and report["input_sets_equal"]
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k
                    in {
                        "strictly_equal",
                        "coverage",
                        "max_position_m",
                        "max_normal_degrees",
                        "environment_equal",
                    }
                },
                indent=2,
            )
        )
        return 0 if report["strictly_equal"] else 1
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    raise SystemExit(main())
