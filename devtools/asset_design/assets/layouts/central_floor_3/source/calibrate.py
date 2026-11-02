"""Calibrate the current third-floor furniture to the approved picture occupancy."""

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists()
)
W = ROOT / "build/asset_design/third-floor-proportions-20261017"
SOURCE = ROOT / "devtools/asset_design/assets/layouts/central_floor_3/source/model.glb"
F = 7.1


def box_of(o):
    ps = [o.matrix_world @ v.co for v in o.data.vertices]
    return [Vector([fn(p[k] for p in ps) for k in range(3)]) for fn in [min, max]]


def group_transform(objects, pivot, scale=(1, 1, 1), offset=(0, 0, 0)):
    pivot = Vector(pivot)
    transform = (
        Matrix.Translation(Vector(offset))
        @ Matrix.Translation(pivot)
        @ Matrix.Diagonal((*scale, 1))
        @ Matrix.Translation(-pivot)
    )
    for o in objects:
        o.matrix_world = transform @ o.matrix_world


def resize_scene():
    objects = {
        o.name: o for o in bpy.data.objects if o.type == "MESH" and o.get("furniture")
    }
    before = {n: [list(v) for v in box_of(o)] for n, o in objects.items()}
    # Keep chair heights and seat heights; change the horizontal body footprint.
    for i, (x, y) in enumerate([(-1.9, -1.05), (1.9, -1.05), (0, 0.85), (0, -2.95)]):
        o = objects["quiet_central_reading_chair_" + str(i)]
        lo, hi = box_of(o)
        s = 1.40 / max(hi.x - lo.x, hi.y - lo.y)
        origin = o.matrix_world.translation.copy()
        pivot = (origin.x, origin.y, F)
        group_transform([o], pivot, (s, s, 1), (x - origin.x, y - origin.y, 0))
    o = objects["quiet_central_reading_table"]
    lo, hi = box_of(o)
    s = 2.10 / (hi.x - lo.x)
    group_transform([o], (0, -1.05, F), (s, s, 1))
    o = objects["quiet_central_reading_rug"]
    lo, hi = box_of(o)
    s = 5.4 / (hi.x - lo.x)
    group_transform([o], (0, -1.05, F), (s, s, 1))
    # Scale the full daybed group so the bed, blanket, pillows and rug stay together.
    bed = objects["quiet_front_sage_daybed"]
    lo, hi = box_of(bed)
    center = (lo + hi) * 0.5
    sx = 5.712 / (hi.x - lo.x)
    sy = 1.651 / (hi.y - lo.y)
    group_transform(
        [o for n, o in objects.items() if n.startswith("quiet_front_")],
        (center.x, center.y, F),
        (sx, sy, 1),
        (-center.x, -6.10 - center.y, 0),
    )
    # Restore the sofa's visual weight while keeping the same window bay.
    sofa = objects["quiet_left_curved_sofa"]
    lo, hi = box_of(sofa)
    center = (lo + hi) * 0.5
    selected = [
        o
        for n, o in objects.items()
        if n == "quiet_left_curved_sofa" or n.startswith("quiet_left_sofa_")
    ]
    group_transform(
        selected,
        (center.x, center.y, F),
        (1.72 / (hi.x - lo.x), 4.18 / (hi.y - lo.y), 1),
        (-5.85 - center.x, -0.10 - center.y, 0),
    )
    for n, o in objects.items():
        if n.startswith("quiet_left_sofa_seat_"):
            lo, hi = box_of(o)
            group_transform(
                [o], (0, 0, lo.z), (1, 1, 0.27 / (hi.z - lo.z)), (0, 0, F + 0.32 - lo.z)
            )
        if n.startswith("quiet_left_sofa_pillow_"):
            lo, hi = box_of(o)
            center = (lo + hi) * 0.5
            group_transform([o], center, (0.42 / (hi.x - lo.x), 1, 1))
    o = objects["quiet_left_conversation_rug"]
    lo, hi = box_of(o)
    center = (lo + hi) * 0.5
    group_transform(
        [o], (center.x, center.y, F), (3.78 / (hi.x - lo.x), 4.75 / (hi.y - lo.y), 1)
    )
    o = objects["quiet_left_tea_table"]
    lo, hi = box_of(o)
    center = (lo + hi) * 0.5
    delta = -4.60 - center.x
    group_transform(
        [o],
        (center.x, center.y, F),
        (1.15 / (hi.x - lo.x), 1.15 / (hi.y - lo.y), 1),
        (delta, 0, 0),
    )
    group_transform(
        [objects["quiet_left_tea_table_cups"]], (0, 0, F), offset=(delta, 0, 0)
    )
    # Reduce the bookcase's angular span on the SAME building-centered arc.
    # Radial depth and vertical dimensions remain fixed; no straight chord shrink.
    library = objects["quiet_rear_library"]
    mesh = library.data
    world = library.matrix_world.copy()
    inverse = world.inverted()
    ps = [world @ v.co for v in mesh.vertices]

    def width(k):
        return max(
            math.hypot(p.x, p.y) * math.sin(math.atan2(p.x, p.y) * k) for p in ps
        ) - min(math.hypot(p.x, p.y) * math.sin(math.atan2(p.x, p.y) * k) for p in ps)

    low, high = 0.25, 1.5
    for _ in range(36):
        middle = (low + high) * 0.5
        if width(middle) < 7.10:
            low = middle
        else:
            high = middle
    k = (low + high) * 0.5
    # Transform imported split normals with the inverse-transpose of the polar map.
    normal_world = world.to_3x3().inverted().transposed()
    normal_local = world.to_3x3().transposed()
    normals = []
    for loop, corner in zip(mesh.loops, mesh.corner_normals):
        p = ps[loop.vertex_index]
        theta = math.atan2(p.x, p.y)
        a = theta * k
        n = normal_world @ corner.vector
        r = n.x * math.sin(theta) + n.y * math.cos(theta)
        t = n.x * math.cos(theta) - n.y * math.sin(theta)
        normals.append(
            (
                normal_local
                @ Vector(
                    (
                        r * math.sin(a) + t / k * math.cos(a),
                        r * math.cos(a) - t / k * math.sin(a),
                        n.z,
                    )
                )
            ).normalized()
        )
    for v, p in zip(mesh.vertices, ps):
        r = math.hypot(p.x, p.y)
        a = math.atan2(p.x, p.y) * k
        v.co = inverse @ Vector((r * math.sin(a), r * math.cos(a), p.z))
    mesh.update()
    mesh.normals_split_custom_set(normals)
    # Keep the rear reading corner visible beside the actual rising stair flight.
    chair = objects["quiet_rear_reading_armchair"]
    lo, hi = box_of(chair)
    dx = 3.0 - (lo.x + hi.x) / 2
    group_transform(
        [
            o
            for n, o in objects.items()
            if n.startswith("quiet_rear_reading_") or n == "quiet_rear_footstool"
        ],
        (0, 0, F),
        offset=(dx, 0, 0),
    )
    return {
        "bookcaseAngularFactor": k,
        "before": before,
        "after": {n: [list(v) for v in box_of(o)] for n, o in objects.items()},
    }


if __name__ == "__main__":
    W.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    report = resize_scene()
    (W / "proportions.json").write_text(json.dumps(report, indent=2))
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(W / "furniture.blend"))
    bpy.ops.export_scene.gltf(
        filepath=str(W / "candidate.glb"),
        export_format="GLB",
        export_extras=True,
        export_yup=True,
        export_materials="EXPORT",
    )
