"""Verify the frozen-source export package without launching an engine."""

import copy
import hashlib
import itertools
import json
import math
import re
import struct
from pathlib import Path

from audit_shared_geometry import require_unique_authoring_geometry

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/godot-asset-migration"
PACKAGE = BUILD / "exported-v044-native"
IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def matrix(node):
    if "matrix" in node:
        return node["matrix"]
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    tx, ty, tz = node.get("translation", [0, 0, 0])
    return [
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
    ]


def multiply(a, b):
    return [
        sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
        for c in range(4)
        for r in range(4)
    ]


def transformed(m, p):
    return [sum(m[k * 4 + r] * p[k] for k in range(3)) + m[12 + r] for r in range(3)]


def check_glb(path, item, inventory, fingerprints):
    with path.open("rb") as stream:
        magic, version, total = struct.unpack("<III", stream.read(12))
        assert (magic, version, total) == (0x46546C67, 2, path.stat().st_size), path
        size, kind = struct.unpack("<II", stream.read(8))
        assert kind == 0x4E4F534A
        document = json.loads(stream.read(size))
        binary_size, binary_kind = struct.unpack("<II", stream.read(8))
        assert binary_kind == 0x004E4942
        assert document["buffers"][0]["byteLength"] <= binary_size
        assert stream.tell() + binary_size == total
        binary = stream.read(binary_size)
    for view in document.get("bufferViews", []):
        assert view.get("byteOffset", 0) + view["byteLength"] <= binary_size
    seen = []
    max_position_error = 0
    max_bounds_error = 0

    def walk(index, parent):
        nonlocal max_position_error, max_bounds_error
        node = document["nodes"][index]
        world = multiply(parent, matrix(node))
        if "mesh" in node:
            source_path = node["extras"]["v044_path"]
            source = inventory[source_path]
            seen.append(source_path)
            error = max(abs(world[12 + i] - source["position"][i]) for i in range(3))
            max_position_error = max(max_position_error, error)
            assert error <= 0.0001, (item["id"], source_path, "position", error)
            local_corners = []
            primitives = document["meshes"][node["mesh"]]["primitives"]
            assert len(primitives) == len(fingerprints[source_path])
            for surface, primitive in enumerate(primitives):
                accessor = document["accessors"][primitive["attributes"]["POSITION"]]
                assert accessor["type"] == "VEC3" and accessor["count"] > 0
                assert accessor["componentType"] == 5126 and not accessor.get(
                    "normalized", False
                )
                view = document["bufferViews"][accessor["bufferView"]]
                offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                stride = view.get("byteStride", 12)
                data = (
                    memoryview(binary)[offset : offset + accessor["count"] * 12]
                    if stride == 12
                    else b"".join(
                        binary[offset + i * stride : offset + i * stride + 12]
                        for i in range(accessor["count"])
                    )
                )
                expected = fingerprints[source_path][surface]
                assert accessor["count"] == expected["vertices"]
                assert (
                    hashlib.sha256(data).hexdigest() == expected["position_sha256"]
                ), (item["id"], source_path, surface, "vertex bytes")
                for corner in itertools.product(*zip(accessor["min"], accessor["max"])):
                    local_corners.append(corner)
            local_low = [min(p[i] for p in local_corners) for i in range(3)]
            local_high = [max(p[i] for p in local_corners) for i in range(3)]
            # Godot transforms the whole mesh AABB, rather than unioning the
            # transformed per-surface boxes. Match that definition exactly.
            points = [
                transformed(world, p)
                for p in itertools.product(*zip(local_low, local_high))
            ]
            low = [min(p[i] for p in points) for i in range(3)]
            high = [max(p[i] for p in points) for i in range(3)]
            expected_low = [
                source["center"][i] - source["size"][i] / 2 for i in range(3)
            ]
            expected_high = [
                source["center"][i] + source["size"][i] / 2 for i in range(3)
            ]
            error = max(
                abs(a - b) for a, b in zip(low + high, expected_low + expected_high)
            )
            assert math.isfinite(error)
            max_bounds_error = max(max_bounds_error, error)
            # Patched native meshes can retain their original surface bounds
            # plus a separate custom culling AABB. glTF recomputes tight bounds;
            # compare actual vertex bytes above, not that engine-only bound.
        for child in node.get("children", []):
            walk(child, world)

    for index in document["scenes"][document.get("scene", 0)]["nodes"]:
        walk(index, IDENTITY)
    assert sorted(seen) == sorted(item["source_paths"]), item["id"]
    assert len(seen) == item["mesh_nodes"]
    return {
        "id": item["id"],
        "nodes": len(seen),
        "max_position_error_m": max_position_error,
        "max_bounds_error_m": max_bounds_error,
    }


def main():
    require_unique_authoring_geometry()
    catalog = json.loads(
        (
            ROOT / "godot_project/tools/nest_authoring/v044-asset-catalog.json"
        ).read_text()
    )
    native = json.loads((PACKAGE / "export-report.json").read_text())
    authoring = json.loads((PACKAGE / "authoring/authoring-report.json").read_text())
    blends = json.loads((PACKAGE / "authoring/blend-report.json").read_text())
    bindings = json.loads((BUILD / "static-export-bindings.json").read_text())
    inventory = {
        n["path"]: n
        for n in json.loads((BUILD / "full-inventory/static-nodes.json").read_text())
    }
    fingerprints = json.loads((BUILD / "source-vertex-fingerprints.json").read_text())
    assert (
        native["passed"]
        and native["sharing_preserved"]
        and not native["full_world_changed_nodes"]
    )
    assert len(native["items"]) == len(bindings["items"]) == 76
    for item in native["items"]:
        model = PACKAGE / "models" / (item["id"] + ".scn")
        wrapper = PACKAGE / "assets" / (item["id"] + ".tscn")
        assert sha(model) == item["sha256"]
        assert item["model"] in wrapper.read_text()
    assert (
        native["snapshot_sha256"]
        == sha(ROOT / catalog["snapshot"])
        == authoring["snapshot_sha256"]
        == blends["snapshot_sha256"]
    )
    assert sha(ROOT / catalog["source_glb"]) == catalog["source_sha256"]
    assert sha(ROOT / catalog["instance_sidecar"]) == catalog["instance_sidecar_sha256"]
    assert blends["passed"] and len(blends["items"]) == len(authoring["items"])
    results = []
    covered = set()
    for item in authoring["items"]:
        path = PACKAGE / "authoring" / (item["id"] + ".glb")
        assert sha(path) == item["sha256"]
        results.append(check_glb(path, item, inventory, fingerprints))
        covered.update(item["source_paths"])
    expected = {
        path for path, node in inventory.items() if node["type"] == "MeshInstance3D"
    }
    assert covered == expected, ("missing source geometry", sorted(expected - covered))
    for item in blends["items"]:
        assert sha(ROOT / item["blend"]) == item["sha256"]
    dependencies = {}

    def dependency(path):
        if path in dependencies:
            return
        assert path.startswith("res://")
        file = ROOT / "godot_project" / path[6:]
        dependencies[path] = sha(file)
        for include in re.findall(r'#include\s+"([^"]+)"', file.read_text()):
            target = (
                include
                if include.startswith("res://")
                else "res://"
                + str((file.parent / include).relative_to(ROOT / "godot_project"))
            )
            dependency(target)

    for path, expected_sha in native["dependencies"].items():
        dependency(path)
        assert dependencies[path] == expected_sha
    report = {
        "passed": True,
        "native_assets": len(native["items"]),
        "glb_libraries": len(results),
        "blend_sources": len(blends["items"]),
        "source_mesh_nodes_covered": len(covered),
        "native_multimesh_batches": native["multimesh_batches"],
        "native_multimesh_instances": native["multimesh_instances"],
        "native_lights": native["lights"],
        "snapshot_sha256": native["snapshot_sha256"],
        "shader_dependencies": dependencies,
        "glb_checks": results,
        "scope": "Static extraction and authoring interchange. Native fingerprints and sharing match V044; GLB vertex bytes, node positions and Blender imports checked. GLB normal encoding, dynamic behavior, new assembly ownership, and rendered visual equivalence are not certified.",
    }
    (PACKAGE / "verification-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    native_by_id = {item["id"]: item for item in native["items"]}
    authoring_by_id = {item["id"]: item for item in authoring["items"]}
    menu = copy.deepcopy(catalog["categories"])

    def attach(items):
        for item in items:
            if "children" in item:
                attach(item["children"])
                continue
            item.pop("artifact", None)
            item.pop("preview", None)
            item["native_scene"] = "assets/" + item["id"] + ".tscn"
            item["source_nodes"] = native_by_id[item["id"]]["checked_nodes"]
            if item["id"] in authoring_by_id:
                item["geometry_exchange"] = "authoring/" + item["id"] + ".glb"
                item["blender_source"] = "authoring/" + item["id"] + ".blend"

    attach(menu)
    (PACKAGE / "asset-index.json").write_text(
        json.dumps(
            {"baseline": "V044", "categories": menu}, ensure_ascii=False, indent=2
        )
        + "\n"
    )
    (PACKAGE / "AGENTS.md").write_text(
        "# V044 静态提取候选\n\n"
        "- 四类菜单与文件入口见 `asset-index.json`；唯一手工清单仍是源码中的 `godot_project/tools/nest_authoring/v044-asset-catalog.json`。\n"
        "- `assets/*.tscn` 引用 `models/*.scn`；`resources/*.res` 保留原生共享资源，禁止分别手改生成资源。\n"
        "- 这些是源范围视图，彼此可能重叠，不能把 76 个视图同时放入世界；正式嵌套组合和独占归属尚未迁移。\n"
        "- `authoring/*.blend` 是从最终 V044 几何重建的编辑候选，非历史原稿；同名 GLB 为交换文件。未恢复程序生成历史或建模修改器。\n"
        "- GLB 顶点字节与节点位置已核对；原生场景保留最终材质、光照、碰撞、植物分批及共享。GLB 往返法线与最终渲染尚未验收。\n"
        "- `retained-placement-variants` 保留未单列菜单的实际几何差异；不为共享目标覆盖差异。\n"
        "- 本包仅为白天、门关闭、床品静止、水相位零的静态提取，不能替代原有动画和交互实现。\n"
        "- 正式场景入口与 V044/V045 备份保留；验收后再迁移运行引用和唯一编辑入口。\n\n"
        "复跑：先编译 `compile_static_asset_export.py`，受控执行 `export_static_assets.gd`、"
        "`export_asset_authoring.gd`、`fingerprint_static_vertices.gd`，再用 Blender 执行 "
        "`rebuild_asset_blends.py`，最后运行 `check_static_asset_export.py`。\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("glb_checks", "shader_dependencies", "scope")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
