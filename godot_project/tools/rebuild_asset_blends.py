"""Run with Blender's bundled bpy; reconstruct editable sources from V044 GLBs."""

import hashlib
import json
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "build/godot-asset-migration/exported-v044-native/authoring"


def main():
    manifest = json.loads((EXPORT / "authoring-report.json").read_text())
    records = []
    for item in manifest["items"]:
        source = EXPORT / (item["id"] + ".glb")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"]
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source))
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        assert len(meshes) == item["mesh_nodes"], (
            item["id"],
            len(meshes),
            item["mesh_nodes"],
        )
        for obj in meshes:
            extras = obj.get("extras", {})
            path = extras.get("v044_path") if hasattr(extras, "get") else None
            path = path or obj.get("v044_path")
            assert path in item["source_paths"], (item["id"], obj.name, path)
            obj["v044_source_path"] = path
        scene = bpy.context.scene
        scene["provenance"] = (
            "Reconstructed from the frozen evaluated V044 scene; not a historical Blender original"
        )
        scene["snapshot_sha256"] = manifest["snapshot_sha256"]
        scene["native_companion"] = "../assets/" + item["id"] + ".tscn"
        scene["limitations"] = (
            "Geometry authoring only. Native shaders, instances, interaction and animation remain in Godot companions. Re-export requires fidelity validation."
        )
        bpy.ops.file.pack_all()
        target = source.with_suffix(".blend")
        bpy.ops.wm.save_as_mainfile(filepath=str(target))
        records.append(
            {
                "id": item["id"],
                "blend": str(target.relative_to(ROOT)),
                "objects": len(meshes),
                "mesh_datablocks": len(bpy.data.meshes),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
        print("REBUILT_BLEND", item["id"], len(meshes), flush=True)
    report = {
        "snapshot_sha256": manifest["snapshot_sha256"],
        "items": records,
        "passed": len(records) == len(manifest["items"]),
    }
    (EXPORT / "blend-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print("BLEND_EXPORT_RESULT", len(records), flush=True)


if __name__ == "__main__":
    main()
