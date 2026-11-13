"""Rebuild the upper wall as continuous surfaces and four identical openings.

Run inside Blender. Read only verified source references; write a new build candidate.
"""

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import delaunay_2d_cdt

ROOT = Path(__file__).resolve().parents[3]
WALL = "Central single continuous full-height envelope"
BOTTOM, TOP = 6.94, 11.66
START = -math.pi / 4
REF_RADIUS = 8.7


def load(path):
    raw = path.read_bytes()
    length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20 : 20 + length])
    binary = raw[28 + length :]
    arrays = []
    for a in doc["accessors"]:
        view = doc["bufferViews"][a["bufferView"]]
        dtype = np.dtype(
            {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}[a["componentType"]]
        )
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        arrays.append(
            np.ndarray(
                (a["count"], width),
                dtype,
                buffer=binary,
                offset=view.get("byteOffset", 0) + a.get("byteOffset", 0),
                strides=(
                    view.get("byteStride", dtype.itemsize * width),
                    dtype.itemsize,
                ),
            ).copy()
        )
    return doc, arrays


def part(doc, name):
    node = next(
        n for n in doc["nodes"] if n.get("extras", {}).get("source_name") == name
    )
    return doc["meshes"][node["mesh"]]["primitives"][0]


def hull(points):
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    points = sorted(set(map(tuple, points)))

    def half(rows):
        out = []
        for p in rows:
            while len(out) > 1 and cross(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]

    return np.array(half(points) + half(points[::-1]))


def save(doc, arrays, path):
    chunks, views, size = [], [], 0
    for a, values in zip(doc["accessors"], arrays):
        pad = bytes(-size % 4)
        chunks.append(pad)
        size += len(pad)
        payload = values.tobytes()
        a["bufferView"] = len(views)
        a.pop("byteOffset", None)
        a["count"] = len(values)
        if "min" in a:
            a["min"], a["max"] = (
                values.min(axis=0).tolist(),
                values.max(axis=0).tolist(),
            )
        views.append({"buffer": 0, "byteOffset": size, "byteLength": len(payload)})
        chunks.append(payload)
        size += len(payload)
    doc["bufferViews"] = views
    doc["buffers"] = [{"byteLength": size}]
    encoded = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary = b"".join(chunks) + bytes(-size % 4)
    path.write_bytes(
        struct.pack(
            "<5I",
            0x46546C67,
            2,
            28 + len(encoded) + len(binary),
            len(encoded),
            0x4E4F534A,
        )
        + encoded
        + struct.pack("<2I", len(binary), 0x004E4942)
        + binary
    )


def smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def main():
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--retained", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    for p in [args.reference, args.retained, Path(bpy.data.filepath)]:
        if not p.resolve().is_relative_to(ROOT):
            raise ValueError("All inputs must belong to this checkout")
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / "build") or out.exists():
        raise ValueError("Use a new output directory under build")
    # Freeze the untouched, evaluated source used for the original curved wall.
    expected = "9fb2e5322fa6bcf7b5b1d8f85636bba57a5cfb9c0a4de9274e662aa92e0ad1eb"
    assert hashlib.sha256(args.reference.read_bytes()).hexdigest() == expected
    original, oa = load(args.reference)
    p = part(original, WALL)
    v = oa[p["attributes"]["POSITION"]]
    f = oa[p["indices"]].reshape(-1, 3)
    tree = BVHTree.FromPolygons(v.tolist(), f.tolist(), all_triangles=True)
    original_positions = v.copy()
    original_normals = oa[p["attributes"]["NORMAL"]].copy()
    original_faces = f.copy()
    heights = np.linspace(BOTTOM, TOP, 234)
    profiles = [[], []]
    residuals = []
    # The untouched pillars contain the original circular cross sections on both skins.
    for side in range(2):
        for y in heights:
            hits = []
            for degree in [41, 45, 49, 131, 135, 139, 221, 225, 229, 311, 315, 319]:
                a = math.radians(degree)
                ray = np.array([math.sin(a), 0, math.cos(a)])
                origin = ray * 20 + [0, y, 0] if side == 0 else np.array([0, y, 0])
                hit = tree.ray_cast(
                    origin.tolist(), (-ray if side == 0 else ray).tolist(), 15
                )[0]
                if hit is None:
                    raise ValueError(f"Missing original wall at {side}, {y}, {degree}")
                hits.append([hit.x, hit.z])
            pts = np.array(hits)
            cx, cz, c = np.linalg.lstsq(
                np.column_stack([2 * pts, np.ones(len(pts))]),
                np.sum(pts * pts, axis=1),
                rcond=None,
            )[0]
            radius = math.sqrt(c + cx * cx + cz * cz)
            residuals.append(
                float(np.max(np.abs(np.linalg.norm(pts - [cx, cz], axis=1) - radius)))
            )
            profiles[side].append([radius, cx, cz])
    profiles = np.array(profiles)
    if max(residuals) > 0.003:
        raise ValueError("Original wall cannot be represented by measured circles")
    print("ORIGINAL_CIRCLE_RESIDUAL", max(residuals), flush=True)

    def parameters(y, side):
        return np.array([np.interp(y, heights, profiles[side, :, k]) for k in range(3)])

    def radial(theta, y, side):
        radius, cx, cz = parameters(y, side)
        # The four shared frames use the northern original profile. Repeat that
        # profile smoothly around the wall, then return to the untouched roof ring.
        local = (theta + math.pi / 4) % (math.pi / 2) - math.pi / 4
        t = abs(local)
        edge = math.pi / 4
        start = edge - 0.025
        cosine = math.cos(t)
        if t > start:
            u = (t - start) / (edge - start)
            a, da = math.cos(start), -math.sin(start) * (edge - start)
            b = math.cos(edge)
            cosine = (
                (2 * u**3 - 3 * u * u + 1) * a
                + (u**3 - 2 * u * u + u) * da
                + (-2 * u**3 + 3 * u * u) * b
            )
        canonical = cz * cosine + math.sqrt(
            radius * radius - cz * cz * (1 - cosine * cosine)
        )
        direction = np.array([math.sin(theta), math.cos(theta)])
        projected = float(np.dot([cx, cz], direction))
        source = projected + math.sqrt(
            radius * radius - cx * cx - cz * cz + projected * projected
        )
        weight = smooth((y - BOTTOM) / 0.18) * (1 - smooth((y - 11.2) / (TOP - 11.2)))
        return source * (1 - weight) + canonical * weight

    def surface(theta, y, side):
        radius = radial(theta, y, side)
        return np.array([radius * math.sin(theta), y, radius * math.cos(theta)])

    def normal(theta, y, side):
        dt, dy = 0.00005, 0.0003
        tangent = surface(theta + dt, y, side) - surface(theta - dt, y, side)
        vertical = surface(theta, min(TOP, y + dy), side) - surface(
            theta, max(BOTTOM, y - dy), side
        )
        n = np.cross(tangent, vertical)
        n /= np.linalg.norm(n)
        return n if side == 0 else -n

    def angle(p):
        return (math.atan2(p[0], p[2]) - START) % math.tau + START

    formal = ROOT / "godot_project/nest/buildings/main/central-building.glb"
    doc, arrays = load(formal)
    wall = part(doc, WALL)
    assert hashlib.sha256(args.retained.read_bytes()).hexdigest() == (
        "3ab0bf52754327ac962438f2b921226bc21e4a77deb4e1ac1985a9075fdf5e46"
    ), "Retained wall reference differs from the verified checkpoint"
    retained, ra = load(args.retained)
    rp = part(retained, WALL)
    old_v, old_n = ra[rp["attributes"]["POSITION"]], ra[rp["attributes"]["NORMAL"]]
    old_f = ra[rp["indices"]].reshape(-1, 3)
    # Remove the previous detached covers by connectivity, not by hiding them.
    parents = list(range(len(old_v)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for a, b, c in old_f:
        parents[root(b)] = root(a)
        parents[root(c)] = root(a)
    groups = {}
    for i in set(old_f.flat):
        groups.setdefault(root(i), []).append(i)
    removed = set()
    for ids in groups.values():
        if len(ids) > 100 and old_v[ids, 1].min() > 7 and old_v[ids, 1].max() < 11.5:
            removed.update(ids)
    old_f = np.array([f for f in old_f if not any(i in removed for i in f)])
    vertices = []
    normals = []
    faces = []
    lookup = {}
    rings = {(h, s): {} for h in [BOTTOM, TOP] for s in range(2)}

    def add(p, n):
        n = np.array(n)
        n /= np.linalg.norm(n)
        key = tuple(np.round(p, 7)) + tuple(np.round(n, 6))
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append(np.array(p))
            normals.append(n)
        return lookup[key]

    def triangle(ids):
        a, b, c = [vertices[i] for i in ids]
        if np.linalg.norm(np.cross(b - a, c - a)) > 1e-11:
            faces.append(ids)

    def clip(poly, height, below):
        result = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            ia = (a[0][1] <= height) if below else (a[0][1] >= height)
            ib = (b[0][1] <= height) if below else (b[0][1] >= height)
            if ia:
                result.append(a)
            if ia != ib:
                t = (height - a[0][1]) / (b[0][1] - a[0][1])
                p = a[0] + t * (b[0] - a[0])
                p[1] = height
                result.append((p, a[1] + t * (b[1] - a[1])))
        return result

    for source_v, source_n, source_f, h, below in [
        (old_v, old_n, old_f, BOTTOM, True),
        (original_positions, original_normals, original_faces, TOP, False),
    ]:
        for face in source_f:
            poly = [
                (source_v[i].astype(float), source_n[i].astype(float)) for i in face
            ]
            if (below and min(p[0][1] for p in poly) > h) or (
                not below and max(p[0][1] for p in poly) < h
            ):
                continue
            clipped = clip(poly, h, below)
            # Insert the unwrap seam into both adjoining retained triangles.
            expanded = []
            for a, b in zip(clipped, clipped[1:] + clipped[:1]):
                expanded.append(a)
                if (
                    abs(a[0][1] - h) < 1e-7
                    and abs(b[0][1] - h) < 1e-7
                    and abs(angle(a[0]) - angle(b[0])) > math.pi
                ):
                    t = -(a[0][0] + a[0][2]) / (
                        (b[0][0] + b[0][2]) - (a[0][0] + a[0][2])
                    )
                    if 1e-8 < t < 1 - 1e-8:
                        expanded.append(
                            (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                        )
            ids = [add(*entry) for entry in expanded]
            if len(ids) > 3:
                # A centre fan preserves collinear seam vertices on every edge.
                center = add(
                    np.mean([p for p, n in expanded], axis=0),
                    np.mean([n for p, n in expanded], axis=0),
                )
                for a, b in zip(ids, ids[1:] + ids[:1]):
                    triangle([center, a, b])
            elif len(ids) == 3:
                triangle(ids)
            for p, n in expanded:
                if abs(p[1] - h) < 1e-7:
                    s = min(
                        range(2),
                        key=lambda s: abs(
                            np.linalg.norm(p[[0, 2]]) - radial(angle(p), h, s)
                        ),
                    )
                    rings[h, s][tuple(np.round(p, 7))] = (p, n)
    print(
        "RETAINED",
        len(faces),
        "RINGS",
        {str(k): len(v) for k, v in rings.items()},
        flush=True,
    )
    # A single inset outline defines all four wall apertures and their reveals.
    frame = part(doc, "Central L3 fitted reveal quadrant 1")
    outline = hull(arrays[frame["attributes"]["POSITION"]][:, :2])
    # Offset each convex edge inward by 25 mm, placing the cut within the frame.
    inset = []
    for i, p in enumerate(outline):
        prev = outline[i - 1]
        nxt = outline[(i + 1) % len(outline)]
        e0 = (p - prev) / np.linalg.norm(p - prev)
        e1 = (nxt - p) / np.linalg.norm(nxt - p)
        n0 = np.array([-e0[1], e0[0]])
        n1 = np.array([-e1[1], e1[0]])
        inset.append(p + np.linalg.solve(np.stack([n0, n1]), np.array([0.025, 0.025])))
    outline = np.array(inset)
    sampled = []
    for a, b in zip(outline, np.roll(outline, -1, axis=0)):
        count = max(1, math.ceil(np.linalg.norm(b - a) / 0.055))
        sampled.extend(a + (b - a) * i / count for i in range(count))
    outline = np.array(sampled)
    hole_positions = {}
    for side in range(2):
        points = []
        edges = []
        overrides = {}
        hole_rings = []

        def loop(
            coords, physical=None, points=points, edges=edges, overrides=overrides
        ):
            start = len(points)
            points.extend(coords)
            ids = list(range(start, len(points)))
            edges.extend((a, b) for a, b in zip(ids, ids[1:] + ids[:1]))
            if physical:
                for idx, value in zip(ids, physical):
                    overrides[idx] = value
            return ids

        boundaries = []
        for h in [BOTTOM, TOP]:
            ring = sorted(rings[h, side].values(), key=lambda pn: angle(pn[0]))
            seam = min(
                ring, key=lambda pn: abs(pn[0][0] + pn[0][2]) if pn[0][2] > 0 else 100
            )
            if abs(seam[0][0] + seam[0][2]) > 1e-5:
                raise ValueError("Missing exact seam vertex")
            middle = [
                pn for pn in ring if abs(pn[0][0] + pn[0][2]) > 1e-6 or pn[0][2] < 0
            ]
            entries = [seam] + middle + [seam]
            coords = (
                [(START * REF_RADIUS, h)]
                + [(angle(p) * REF_RADIUS, h) for p, n in middle]
                + [((START + math.tau) * REF_RADIUS, h)]
            )
            boundaries.append((coords, entries))
        left = [
            (START * REF_RADIUS, y) for y in np.arange(BOTTOM + 0.06, TOP - 0.001, 0.06)
        ]
        right = [((START + math.tau) * REF_RADIUS, y) for _, y in left]
        coords = boundaries[0][0] + right + boundaries[1][0][::-1] + left[::-1]
        physical = (
            boundaries[0][1]
            + [
                (surface(s / REF_RADIUS, y, side), normal(s / REF_RADIUS, y, side))
                for s, y in right
            ]
            + boundaries[1][1][::-1]
            + [
                (surface(s / REF_RADIUS, y, side), normal(s / REF_RADIUS, y, side))
                for s, y in left[::-1]
            ]
        )
        loop(coords, physical)
        for q in range(4):
            coords = []
            positions = []
            for x, y in outline:
                radius, cx, cz = parameters(y, side)
                z = cz + math.sqrt(radius * radius - x * x)
                theta = math.atan2(x, z) + q * math.pi / 2
                coords.append((theta * REF_RADIUS, y))
                positions.append(surface(theta, y, side))
            ids = loop(coords)
            hole_rings.append(np.array(coords))
            hole_positions[side, q] = positions
            for idx, position, (s, y) in zip(ids, positions, coords):
                overrides[idx] = (position, normal(s / REF_RADIUS, y, side))

        def in_hole(p, hole_rings=hole_rings):
            # Winding remains valid after mapping the planar outline onto the curved skin.
            for poly in hole_rings:
                if (
                    p[0] < poly[:, 0].min()
                    or p[0] > poly[:, 0].max()
                    or p[1] < poly[:, 1].min()
                    or p[1] > poly[:, 1].max()
                ):
                    continue
                end = np.roll(poly, -1, axis=0)
                crossing = (poly[:, 1] > p[1]) != (end[:, 1] > p[1])
                a, b = poly[crossing], end[crossing]
                hits = a[:, 0] + (p[1] - a[:, 1]) * (b[:, 0] - a[:, 0]) / (
                    b[:, 1] - a[:, 1]
                )
                if int(np.sum(hits > p[0])) % 2:
                    return True
            return False

        for y in np.arange(BOTTOM + 0.07, TOP - 0.025, 0.07):
            for s in np.arange(
                START * REF_RADIUS + 0.105,
                (START + math.tau) * REF_RADIUS - 0.025,
                0.105,
            ):
                if not in_hole(np.array([s, y])):
                    points.append((s, y))
        print("CDT_INPUT", side, len(points), flush=True)
        result = delaunay_2d_cdt([Vector(p) for p in points], edges, [], 0, 1e-7, True)
        cpoints, _, cfaces, orig, _, _ = result
        ids = []
        for coord, source_ids in zip(cpoints, orig):
            special = next((overrides[i] for i in source_ids if i in overrides), None)
            s, y = coord
            ids.append(
                add(
                    *(
                        special
                        if special
                        else (
                            surface(s / REF_RADIUS, y, side),
                            normal(s / REF_RADIUS, y, side),
                        )
                    )
                )
            )
        count = 0
        for face in cfaces:
            center = np.mean([cpoints[i] for i in face], axis=0)
            if in_hole(center):
                continue
            f = [ids[i] for i in face]
            if side:
                f.reverse()
            triangle(f)
            count += 1
        print("CDT_FACES", side, count, flush=True)
    # Connect the two skins through each aperture. These are real wall reveals.
    for q in range(4):
        outside = np.array(hole_positions[0, q])
        inside = np.array(hole_positions[1, q])
        for i in range(len(outside)):
            j = (i + 1) % len(outside)
            p = [outside[i], outside[j], inside[j], inside[i]]
            n = np.cross(p[1] - p[0], p[2] - p[0])
            n /= np.linalg.norm(n)
            ids = [add(v, n) for v in p]
            triangle([ids[0], ids[1], ids[2]])
            triangle([ids[0], ids[2], ids[3]])
    vertices = np.array(vertices, dtype="<f4")
    normals = np.array(normals, dtype="<f4")
    faces = np.array(faces, dtype="<u4")
    used = np.unique(faces)
    mapping = np.zeros(len(vertices), dtype="<u4")
    mapping[used] = np.arange(len(used))
    arrays[wall["attributes"]["POSITION"]] = vertices[used]
    arrays[wall["attributes"]["NORMAL"]] = normals[used]
    arrays[wall["indices"]] = mapping[faces].reshape(-1, 1)
    out.mkdir(parents=True)
    save(doc, arrays, out / "central-building.glb")
    # Only replace the wall data in the existing authoring workfile.
    obj = next(ob for ob in bpy.data.objects if ob.get("source_name") == WALL)
    old_objects = set(bpy.data.objects)
    old_data = {k: set(getattr(bpy.data, k)) for k in ["meshes", "materials", "images"]}
    bpy.ops.import_scene.gltf(
        filepath=str(out / "central-building.glb"),
        import_pack_images=True,
        merge_vertices=False,
    )
    imported = set(bpy.data.objects) - old_objects
    replacement = next(ob for ob in imported if ob.get("source_name") == WALL)
    assert all(
        abs(obj.matrix_world[r][c] - replacement.matrix_world[r][c]) < 1e-5
        for r in range(4)
        for c in range(4)
    )
    materials = list(obj.data.materials)
    obj.data = replacement.data
    obj.data.materials.clear()
    for material in materials:
        obj.data.materials.append(material)
    for ob in imported:
        bpy.data.objects.remove(ob, do_unlink=True)
    for kind, old in old_data.items():
        data = getattr(bpy.data, kind)
        for item in set(data) - old:
            if item.users == 0:
                data.remove(item)
    if "facade_window_fit" in obj:
        del obj["facade_window_fit"]
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(
        filepath=str(out / "central-building.blend"), compress=True
    )
    report = {
        "original_reference_sha256": expected,
        "retained_reference_sha256": hashlib.sha256(
            args.retained.read_bytes()
        ).hexdigest(),
        "wall_band": [BOTTOM, TOP],
        "original_circle_fit_max_error_m": max(residuals),
        "wall_vertices": len(used),
        "wall_triangles": len(faces),
        "apertures": 4,
        "outline_vertices": len(outline),
        "candidate_sha256": hashlib.sha256(
            (out / "central-building.glb").read_bytes()
        ).hexdigest(),
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("REBUILT", report, flush=True)


if __name__ == "__main__":
    main()
