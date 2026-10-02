"""验证 Shape Key 在 Blender 依赖图和导出结果中确实产生顶点位移。"""

from __future__ import annotations

import bpy


def reset_keys(mesh: bpy.types.Object) -> None:
    for key in mesh.data.shape_keys.key_blocks:
        key.value = 0.0
    mesh.data.update()
    bpy.context.view_layer.update()


def evaluated_vertex_world(
    mesh: bpy.types.Object, index: int
) -> tuple[float, float, float]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh.evaluated_get(depsgraph)
    evaluated_mesh = evaluated.to_mesh()
    try:
        point = evaluated.matrix_world @ evaluated_mesh.vertices[index].co
        return point.x, point.y, point.z
    finally:
        evaluated.to_mesh_clear()


def distance(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    return sum((a - b) ** 2 for a, b in zip(first, second)) ** 0.5


def main() -> None:
    mesh = max(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"),
        key=lambda item: len(item.data.vertices),
    )
    keys = mesh.data.shape_keys.key_blocks
    basis = keys["Basis"]
    reset_keys(mesh)

    failures: list[str] = []
    for key in keys[1:]:
        max_index = max(
            range(len(mesh.data.vertices)),
            key=lambda index: (
                (key.data[index].co - basis.data[index].co).length_squared
            ),
        )
        stored_delta = (key.data[max_index].co - basis.data[max_index].co).length
        before = evaluated_vertex_world(mesh, max_index)
        key.value = 1.0
        mesh.data.update()
        bpy.context.view_layer.update()
        after = evaluated_vertex_world(mesh, max_index)
        evaluated_delta = distance(before, after)
        print(
            f"MORPH_VALIDATION name={key.name} index={max_index} "
            f"stored_local={stored_delta:.6f} evaluated_world={evaluated_delta:.6f}"
        )
        if evaluated_delta < 0.0001:
            failures.append(key.name)
        reset_keys(mesh)

    if failures:
        raise RuntimeError("Shape Key 未进入 evaluated mesh: " + ", ".join(failures))
    print(f"MORPH_VALIDATION_DONE count={len(keys) - 1}")


if __name__ == "__main__":
    main()
