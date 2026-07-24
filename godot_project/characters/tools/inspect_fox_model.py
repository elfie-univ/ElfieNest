"""导入狐狸 GLB，输出结构诊断并渲染四视图。"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Vector


def project_root() -> Path:
    marker = Path("godot_project/characters/fox/fox.glb")
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / marker).is_file():
            return candidate
    raise RuntimeError("无法定位 ElfieNest 项目根目录")


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def world_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    corners = [
        obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box
    ]
    return (
        Vector(
            (
                min(v.x for v in corners),
                min(v.y for v in corners),
                min(v.z for v in corners),
            )
        ),
        Vector(
            (
                max(v.x for v in corners),
                max(v.y for v in corners),
                max(v.z for v in corners),
            )
        ),
    )


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )


def add_camera(location: Vector, target: Vector) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new("PreviewCamera")
    camera_data.lens = 58
    camera = bpy.data.objects.new("PreviewCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    look_at(camera, target)
    bpy.context.scene.camera = camera
    return camera


def add_lights(center: Vector, size: float) -> None:
    for name, location, energy, area_size in (
        ("Key", center + Vector((-size, -size, size * 1.5)), 1000.0, size * 1.7),
        ("Fill", center + Vector((size, -size * 0.4, size)), 650.0, size * 1.4),
        ("Rim", center + Vector((0, size, size * 1.4)), 850.0, size * 1.2),
    ):
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = area_size
        light = bpy.data.objects.new(name, light_data)
        bpy.context.scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (center - location).to_track_quat("-Z", "Y").to_euler()


def configure_render(output_dir: Path) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.filepath = str(output_dir / "neutral.png")
    scene.world.color = (0.055, 0.065, 0.08)


def main() -> None:
    root = project_root()
    input_path = root / "godot_project/characters/fox/fox.glb"
    output_dir = root / "godot_project/characters/fox/source/previews/neutral"
    output_dir.mkdir(parents=True, exist_ok=True)

    clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(input_path))

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not meshes or len(armatures) != 1:
        raise RuntimeError(
            f"预期至少一个网格和一个骨架，实际为 {len(meshes)} / {len(armatures)}"
        )

    mesh = max(meshes, key=lambda item: len(item.data.vertices))
    armature = armatures[0]
    minimum, maximum = world_bounds([mesh])
    center = (minimum + maximum) * 0.5
    size = max((maximum - minimum).x, (maximum - minimum).y, (maximum - minimum).z)

    for item in sorted(meshes, key=lambda obj: len(obj.data.vertices), reverse=True):
        print(
            f"FOX_MESH name={item.name} vertices={len(item.data.vertices)} "
            f"polygons={len(item.data.polygons)} groups={len(item.vertex_groups)} "
            f"parent={item.parent.name if item.parent else '-'} hide_render={item.hide_render}"
        )
        if item != mesh:
            item.hide_render = True
    print(
        f"FOX_BOUNDS min={tuple(round(v, 5) for v in minimum)} max={tuple(round(v, 5) for v in maximum)}"
    )
    print(f"FOX_ARMATURE name={armature.name} bones={len(armature.data.bones)}")
    print("FOX_BONES " + ",".join(bone.name for bone in armature.data.bones))
    print("FOX_VERTEX_GROUPS " + ",".join(group.name for group in mesh.vertex_groups))

    configure_render(output_dir)
    add_lights(center, size)
    distance = size * 2.1
    camera = add_camera(center + Vector((0, -distance, size * 0.05)), center)
    views = {
        "front_neg_y": Vector((0, -distance, size * 0.05)),
        "back_pos_y": Vector((0, distance, size * 0.05)),
        "left_neg_x": Vector((-distance, 0, size * 0.05)),
        "right_pos_x": Vector((distance, 0, size * 0.05)),
    }
    for name, offset in views.items():
        camera.location = center + offset
        look_at(camera, center)
        bpy.context.scene.render.filepath = str(output_dir / f"{name}.png")
        bpy.ops.render.render(write_still=True)

    blend_path = root / "godot_project/characters/fox/source/fox_neutral_import.blend"
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"FOX_INSPECTION_DONE output={output_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FOX_INSPECTION_ERROR {exc}", file=sys.stderr)
        raise
