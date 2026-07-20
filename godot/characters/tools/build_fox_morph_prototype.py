"""为现有狐狸模型生成六组程序化 Shape Key 原型和预览图。"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


Deformer = Callable[[Vector, bpy.types.MeshVertex], Vector]


def project_root() -> Path:
    marker = Path("godot/characters/fox/fox.glb")
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / marker).is_file():
            return candidate
    raise RuntimeError("无法定位 ElfieNest 项目根目录")


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def ellipsoid_weight(point: Vector, center: Vector, radii: Vector) -> float:
    normalized = Vector(
        (
            (point.x - center.x) / radii.x,
            (point.y - center.y) / radii.y,
            (point.z - center.z) / radii.z,
        )
    )
    distance_squared = normalized.length_squared
    if distance_squared >= 1.0:
        return 0.0
    return smoothstep(1.0 - distance_squared)


def group_weight(
    mesh: bpy.types.Object,
    vertex: bpy.types.MeshVertex,
    names: tuple[str, ...],
) -> float:
    indices = {mesh.vertex_groups[name].index for name in names if name in mesh.vertex_groups}
    return min(1.0, sum(item.weight for item in vertex.groups if item.group in indices) * 2.0)


def bone_head_in_world(
    _mesh: bpy.types.Object,
    armature: bpy.types.Object,
    bone_name: str,
) -> Vector:
    return armature.matrix_world @ armature.data.bones[bone_name].head_local


def closest_point_on_segment(point: Vector, start: Vector, end: Vector) -> Vector:
    segment = end - start
    length_squared = segment.length_squared
    if length_squared <= 1e-12:
        return start
    amount = max(0.0, min(1.0, (point - start).dot(segment) / length_squared))
    return start + segment * amount


def add_shape_key(
    mesh: bpy.types.Object,
    name: str,
    deform: Deformer,
) -> tuple[int, float]:
    key = mesh.shape_key_add(name=name, from_mix=False)
    key.value = 0.0
    key.slider_min = 0.0
    key.slider_max = 1.0
    affected = 0
    maximum_delta = 0.0
    world_to_local = mesh.matrix_world.inverted().to_3x3()
    for vertex in mesh.data.vertices:
        original = vertex.co.copy()
        world_point = mesh.matrix_world @ original
        world_delta = deform(world_point, vertex)
        if world_delta.length_squared > 1e-12:
            key.data[vertex.index].co = original + world_to_local @ world_delta
            affected += 1
            maximum_delta = max(maximum_delta, world_delta.length)
    mesh.data.update()
    print(f"MORPH_CREATED name={name} affected={affected} max_delta={maximum_delta:.5f}")
    return affected, maximum_delta


def make_belly_deformer(direction: float) -> Deformer:
    center = Vector((0.0, -0.015, 0.88))
    radii = Vector((0.35, 0.34, 0.42))
    magnitude = 0.110 if direction > 0 else 0.070

    def deform(point: Vector, _vertex: bpy.types.MeshVertex) -> Vector:
        weight = ellipsoid_weight(point, center, radii)
        if weight <= 0.0:
            return Vector()
        radial = Vector((point.x - center.x, point.y - center.y, 0.0))
        if radial.length_squared <= 1e-10:
            radial = Vector((0.0, -1.0, 0.0))
        radial.normalize()
        front_emphasis = 1.0 + 0.35 * smoothstep((-point.y + 0.02) / 0.30)
        return radial * magnitude * weight * front_emphasis * direction

    return deform


def make_arm_deformer(
    mesh: bpy.types.Object,
    armature: bpy.types.Object,
    direction: float,
) -> Deformer:
    segment_names = (
        ("mixamorig:LeftArm", "mixamorig:LeftForeArm"),
        ("mixamorig:LeftForeArm", "mixamorig:LeftHand"),
        ("mixamorig:RightArm", "mixamorig:RightForeArm"),
        ("mixamorig:RightForeArm", "mixamorig:RightHand"),
    )
    segments = [
        (bone_head_in_world(mesh, armature, start), bone_head_in_world(mesh, armature, end))
        for start, end in segment_names
    ]
    arm_groups = tuple({name for pair in segment_names for name in pair[:-1]})
    factor = 0.35 if direction > 0 else 0.22

    def deform(point: Vector, vertex: bpy.types.MeshVertex) -> Vector:
        weight = group_weight(mesh, vertex, arm_groups)
        if weight <= 0.02:
            return Vector()
        closest = min(
            (closest_point_on_segment(point, start, end) for start, end in segments),
            key=lambda candidate: (point - candidate).length_squared,
        )
        radial = point - closest
        if radial.length_squared <= 1e-12:
            return Vector()
        return radial * factor * weight * direction

    return deform


def make_skull_deformer(mesh: bpy.types.Object, direction: float) -> Deformer:
    factor = 0.20 if direction > 0 else 0.14

    def deform(point: Vector, vertex: bpy.types.MeshVertex) -> Vector:
        weight = group_weight(mesh, vertex, ("mixamorig:Head",))
        weight *= smoothstep((point.z - 1.20) / 0.18)
        weight *= smoothstep((1.80 - point.z) / 0.18)
        if point.z > 1.64 and abs(point.x) > 0.17:
            weight *= smoothstep((1.76 - point.z) / 0.12)
        return Vector((point.x * factor * weight * direction, 0.0, 0.0))

    return deform


def make_cheek_deformer(mesh: bpy.types.Object, direction: float) -> Deformer:
    centers = (
        Vector((-0.18, -0.27, 1.40)),
        Vector((0.18, -0.27, 1.40)),
    )
    radii = Vector((0.25, 0.30, 0.24))
    scale = 1.0 if direction > 0 else 0.72

    def deform(point: Vector, vertex: bpy.types.MeshVertex) -> Vector:
        weights = [ellipsoid_weight(point, center, radii) for center in centers]
        index = 0 if weights[0] >= weights[1] else 1
        weight = weights[index] * group_weight(mesh, vertex, ("mixamorig:Head",))
        if weight <= 0.0:
            return Vector()
        side = -1.0 if centers[index].x < 0.0 else 1.0
        return Vector((side * 0.065, -0.045, 0.008)) * weight * scale * direction

    return deform


def make_muzzle_deformer(mesh: bpy.types.Object, direction: float) -> Deformer:
    center = Vector((0.0, -0.39, 1.36))
    radii = Vector((0.28, 0.24, 0.23))
    magnitude = 0.110 if direction > 0 else 0.075

    def deform(point: Vector, vertex: bpy.types.MeshVertex) -> Vector:
        if point.y > -0.20:
            return Vector()
        weight = ellipsoid_weight(point, center, radii)
        weight *= group_weight(mesh, vertex, ("mixamorig:Head",))
        return Vector((0.0, -magnitude * weight * direction, 0.0))

    return deform


def make_eye_socket_deformer(mesh: bpy.types.Object, direction: float) -> Deformer:
    centers = (
        Vector((-0.135, -0.38, 1.565)),
        Vector((0.135, -0.38, 1.565)),
    )
    radii = Vector((0.19, 0.18, 0.18))
    factor = 0.25 if direction > 0 else 0.16

    def deform(point: Vector, vertex: bpy.types.MeshVertex) -> Vector:
        weights = [ellipsoid_weight(point, center, radii) for center in centers]
        index = 0 if weights[0] >= weights[1] else 1
        weight = weights[index] * group_weight(mesh, vertex, ("mixamorig:Head",))
        if weight <= 0.0:
            return Vector()
        center = centers[index]
        offset = point - center
        radial = Vector((offset.x, 0.0, offset.z))
        forward = Vector((0.0, -0.018, 0.0)) if direction > 0 else Vector()
        return (radial * factor + forward) * weight * direction

    return deform


def world_bounds(mesh: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box]
    return (
        Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners))),
        Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners))),
    )


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def configure_preview_scene(mesh: bpy.types.Object) -> tuple[bpy.types.Object, Vector, float]:
    minimum, maximum = world_bounds(mesh)
    center = (minimum + maximum) * 0.5
    size = max((maximum - minimum).x, (maximum - minimum).y, (maximum - minimum).z)

    camera_data = bpy.data.cameras.new("MorphPreviewCamera")
    camera_data.lens = 58
    camera = bpy.data.objects.new("MorphPreviewCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera

    for name, location, energy, area_size in (
        ("MorphKey", center + Vector((-size, -size, size * 1.5)), 1000.0, size * 1.7),
        ("MorphFill", center + Vector((size, -size * 0.4, size)), 650.0, size * 1.4),
        ("MorphRim", center + Vector((0, size, size * 1.4)), 850.0, size * 1.2),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = area_size
        light = bpy.data.objects.new(name, light_data)
        bpy.context.scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (center - location).to_track_quat("-Z", "Y").to_euler()

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 384
    scene.render.resolution_y = 384
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.055, 0.065, 0.08)
    return camera, center, size


def reset_shape_keys(mesh: bpy.types.Object) -> None:
    if mesh.data.shape_keys is None:
        return
    for key in mesh.data.shape_keys.key_blocks:
        key.value = 0.0


def render_previews(
    mesh: bpy.types.Object,
    output_dir: Path,
    variant_filter: set[str] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    camera, center, size = configure_preview_scene(mesh)
    distance = size * 2.1
    head_center = Vector((0.0, -0.04, 1.52))
    views = {
        "front": (center, center + Vector((0.0, -distance, size * 0.05))),
        "side": (center, center + Vector((-distance, 0.0, size * 0.05))),
        "head_front": (head_center, head_center + Vector((0.0, -1.80, 0.02))),
        "head_side": (head_center, head_center + Vector((-1.80, 0.0, 0.02))),
    }
    variants: list[tuple[str, dict[str, float]]] = [("Basis", {})]
    variants.extend(
        (key.name, {key.name: 1.0}) for key in mesh.data.shape_keys.key_blocks[1:]
    )
    variants.extend(
        (
            (
                "Combined_Round",
                {
                    "Body_BellyDepth_Pos": 0.80,
                    "Body_ArmThickness_Pos": 0.60,
                    "Face_SkullWidth_Pos": 0.55,
                    "Face_CheekFullness_Pos": 0.85,
                    "Face_MuzzleLength_Neg": 0.35,
                    "Face_EyeSocketSize_Pos": 0.55,
                },
            ),
            (
                "Combined_Lean",
                {
                    "Body_BellyDepth_Neg": 0.75,
                    "Body_ArmThickness_Neg": 0.55,
                    "Face_SkullWidth_Neg": 0.45,
                    "Face_CheekFullness_Neg": 0.60,
                    "Face_MuzzleLength_Pos": 0.85,
                    "Face_EyeSocketSize_Neg": 0.25,
                },
            ),
        )
    )
    if variant_filter is not None:
        variants = [item for item in variants if item[0] in variant_filter]
    for variant, weights in variants:
        reset_shape_keys(mesh)
        for key_name, value in weights.items():
            mesh.data.shape_keys.key_blocks[key_name].value = value
        mesh.data.update()
        bpy.context.view_layer.update()
        for view_name, (target, location) in views.items():
            camera.location = location
            look_at(camera, target)
            bpy.context.scene.render.filepath = str(output_dir / f"{variant}__{view_name}.png")
            bpy.ops.render.render(write_still=True)
    reset_shape_keys(mesh)


def export_prototype(
    mesh: bpy.types.Object,
    armature: bpy.types.Object,
    output_path: Path,
) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        use_selection=True,
        export_animations=False,
        export_morph=True,
        export_morph_normal=False,
        export_morph_tangent=False,
    )


def configure_inspection_workspace(
    mesh: bpy.types.Object,
    armature: bpy.types.Object,
) -> None:
    """保存一个打开后能直接检查网格和 Shape Key 的 Blender 工作区。"""
    reset_shape_keys(mesh)
    bpy.ops.object.select_all(action="DESELECT")
    armature.show_in_front = False
    armature.data.display_type = "STICK"
    armature.hide_set(True)
    mesh.hide_set(False)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    mesh.active_shape_key_index = 0

    front_rotation = Quaternion((math.sqrt(0.5), math.sqrt(0.5), 0.0, 0.0))
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.region_3d.view_location = Vector((0.0, 0.0, 0.95))
                space.region_3d.view_distance = 2.6
                space.region_3d.view_rotation = front_rotation
                space.region_3d.view_perspective = "ORTHO"
                space.shading.type = "MATERIAL"
                space.clip_start = 0.01
                space.clip_end = 100.0
            elif area.type == "PROPERTIES":
                area.spaces.active.context = "DATA"


def main() -> None:
    root = project_root()
    input_path = root / "godot/characters/fox/fox.glb"
    source_dir = root / "godot/characters/fox/source"
    preview_dir = source_dir / "previews/morph_prototype"
    blend_path = source_dir / "fox_morph_prototype.blend"
    glb_path = source_dir / "fox_morph_prototype.glb"
    source_dir.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not meshes or len(armatures) != 1:
        raise RuntimeError(f"狐狸结构异常：mesh={len(meshes)} armature={len(armatures)}")
    mesh = max(meshes, key=lambda item: len(item.data.vertices))
    armature = armatures[0]
    for item in list(meshes):
        if item != mesh:
            bpy.data.objects.remove(item, do_unlink=True)

    if mesh.data.shape_keys is not None:
        raise RuntimeError("正式狐狸已经包含 Shape Key，原型脚本拒绝覆盖")
    mesh.shape_key_add(name="Basis", from_mix=False)

    add_shape_key(mesh, "Body_BellyDepth_Pos", make_belly_deformer(1.0))
    add_shape_key(mesh, "Body_BellyDepth_Neg", make_belly_deformer(-1.0))
    add_shape_key(mesh, "Body_ArmThickness_Pos", make_arm_deformer(mesh, armature, 1.0))
    add_shape_key(mesh, "Body_ArmThickness_Neg", make_arm_deformer(mesh, armature, -1.0))
    add_shape_key(mesh, "Face_SkullWidth_Pos", make_skull_deformer(mesh, 1.0))
    add_shape_key(mesh, "Face_SkullWidth_Neg", make_skull_deformer(mesh, -1.0))
    add_shape_key(mesh, "Face_CheekFullness_Pos", make_cheek_deformer(mesh, 1.0))
    add_shape_key(mesh, "Face_CheekFullness_Neg", make_cheek_deformer(mesh, -1.0))
    add_shape_key(mesh, "Face_MuzzleLength_Pos", make_muzzle_deformer(mesh, 1.0))
    add_shape_key(mesh, "Face_MuzzleLength_Neg", make_muzzle_deformer(mesh, -1.0))
    add_shape_key(mesh, "Face_EyeSocketSize_Pos", make_eye_socket_deformer(mesh, 1.0))
    add_shape_key(mesh, "Face_EyeSocketSize_Neg", make_eye_socket_deformer(mesh, -1.0))

    render_previews(mesh, preview_dir, {"Basis"})
    reset_shape_keys(mesh)
    export_prototype(mesh, armature, glb_path)

    for obj in list(bpy.context.scene.objects):
        if obj.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    configure_inspection_workspace(mesh, armature)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"MORPH_PROTOTYPE_DONE blend={blend_path} glb={glb_path} previews={preview_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"MORPH_PROTOTYPE_ERROR {exc}", file=sys.stderr)
        raise
