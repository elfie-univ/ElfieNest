"""Reconstruct a Blender workfile or export a review GLB. Run inside Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from urllib.parse import unquote

import bpy

ROOT = Path(__file__).resolve().parents[3]
BUILDINGS = ROOT / "godot_project/nest/buildings"
OUTPUT = ROOT / "build/godot_assets/nest-authoring"
ASSETS = {"main": "central-building", "pod": "pod-building"}


def read_glb(path: Path) -> tuple[dict, bytes, str]:
    raw = path.read_bytes()
    magic, version, size, length, kind = struct.unpack_from("<4s4I", raw)
    if (magic, version, size, kind) != (b"glTF", 2, len(raw), 0x4E4F534A):
        raise ValueError(f"Not a GLB 2.0 model: {path}")
    return (
        json.loads(raw[20 : 20 + length]),
        raw[28 + length :],
        hashlib.sha256(raw).hexdigest(),
    )


def mesh_counts(document: dict, binary: bytes) -> tuple[int, int, int]:
    pending = list(document["scenes"][document.get("scene", 0)]["nodes"])
    meshes = triangles = valid_triangles = 0
    seen = set()
    counts = {}
    while pending:
        index = pending.pop()
        if index in seen:
            continue
        seen.add(index)
        node = document["nodes"][index]
        pending.extend(node.get("children", []))
        if "mesh" not in node:
            continue
        meshes += 1
        mesh = node["mesh"]
        if mesh not in counts:
            total = valid = 0
            for part in document["meshes"][mesh]["primitives"]:
                if part.get("mode", 4) != 4 or "indices" not in part:
                    raise ValueError("The building workfile requires indexed triangles")
                accessor = document["accessors"][part["indices"]]
                view = document["bufferViews"][accessor["bufferView"]]
                fmt = {5121: "<3B", 5123: "<3H", 5125: "<3I"}[accessor["componentType"]]
                count = accessor["count"] // 3
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                end = start + count * struct.calcsize(fmt)
                faces = set()
                for a, b, c in struct.iter_unpack(fmt, binary[start:end]):
                    if a != b and b != c and a != c:
                        faces.add(tuple(sorted((a, b, c))))
                total += count
                valid += len(faces)
            counts[mesh] = (total, valid)
        total, valid = counts[mesh]
        triangles += total
        valid_triangles += valid
    return meshes, triangles, valid_triangles


def reconstruct(model: Path, destination: Path) -> None:
    document, binary, digest = read_glb(model)
    for image in document.get("images", []):
        uri = image.get("uri")
        if uri and not uri.startswith("data:"):
            texture = (model.parent / unquote(uri)).resolve()
            if not texture.is_relative_to(BUILDINGS) or not texture.is_file():
                raise ValueError(f"Missing building texture: {uri}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = bpy.ops.import_scene.gltf(
        filepath=str(model), import_pack_images=True, merge_vertices=False
    )
    if result != {"FINISHED"}:
        raise RuntimeError(f"Blender could not import {model}")
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    triangles = sum(len(obj.data.polygons) for obj in objects)
    expected_objects, indexed, valid = mesh_counts(document, binary)
    # Blender's mesh validator removes repeated-index and duplicate faces.
    if len(objects) != expected_objects or triangles not in {indexed, valid}:
        raise ValueError(
            f"Unexpected Blender geometry: {len(objects)} vs {expected_objects} "
            f"mesh placements; {triangles} vs {indexed} indexed / {valid} valid faces"
        )
    if any(len(face.vertices) != 3 for obj in objects for face in obj.data.polygons):
        raise ValueError("Blender changed the triangle topology during import")
    bpy.ops.file.pack_all()
    unpacked = [
        image.name
        for image in bpy.data.images
        if image.source == "FILE" and not image.packed_files
    ]
    if unpacked:
        raise ValueError(f"Unpacked textures: {unpacked}")

    scene = bpy.context.scene
    scene["elfienest_model"] = model.relative_to(ROOT).as_posix()
    scene["elfienest_import_sha256"] = digest
    scene["elfienest_mesh_placements"] = len(objects)
    scene["elfienest_triangles"] = triangles
    scene["elfienest_original_indexed_triangles"] = indexed
    reference = bpy.data.texts.new("ElfieNest source GLB metadata")
    reference.write(json.dumps(document, ensure_ascii=False, indent=2))
    reference.use_fake_user = True
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), compress=True)
    print(
        f"Saved {destination}: {len(objects)} mesh placements, "
        f"{triangles} faces ({indexed} source triangles)"
    )


def export_candidate(model: Path, destination: Path) -> None:
    source = model.parent / "source" / f"{model.stem}.blend"
    if Path(bpy.data.filepath).resolve() != source:
        raise ValueError(f"Open the building workfile first: {source}")
    if bpy.context.scene.get("elfienest_model") != model.relative_to(ROOT).as_posix():
        raise ValueError(f"The open workfile is not for {model.name}")
    result = bpy.ops.export_scene.gltf(
        filepath=str(destination),
        export_format="GLB",
        export_extras=True,
        export_tangents=True,
        export_animations=False,
    )
    if result != {"FINISHED"} or not destination.is_file():
        raise RuntimeError("Blender did not export the review model")
    print(f"Saved Blender review candidate: {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("reconstruct", "export-candidate"))
    parser.add_argument("building", choices=ASSETS)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    destination = args.output.resolve()
    if not destination.is_relative_to(OUTPUT):
        parser.error(f"Write candidates beneath {OUTPUT}")
    extension = ".blend" if args.action == "reconstruct" else ".glb"
    if destination.suffix != extension or destination.exists():
        parser.error(f"Specify a new {extension} file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    model = BUILDINGS / args.building / (ASSETS[args.building] + ".glb")
    action = reconstruct if args.action == "reconstruct" else export_candidate
    action(model, destination)


if __name__ == "__main__":
    main()
