"""Build the named GLB files for the reviewed Nest menu."""

import copy
import hashlib
import mmap
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from audit_shared_geometry import AUTHORING, glb_meshes
from export_shared_asset_sources import Library, read_document

DESK_IDS = ("desk-a", "desk-b", "desk-c", "desk-d")
DESK_LIBRARY = "bedroom-desks"


def material_signature(document, library, mesh):
    def normalize(value):
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key.endswith("Texture") and isinstance(item, dict) and "index" in item:
                texture = document["textures"][item["index"]]
                image = document["images"][texture["source"]]
                if "bufferView" in image:
                    payload = library.view_bytes(
                        document["bufferViews"][image["bufferView"]]
                    )
                else:
                    payload = (library.textures / Path(image["uri"]).name).read_bytes()
                sampler = texture.get("sampler")
                result[key] = {
                    **{k: v for k, v in item.items() if k != "index"},
                    "image": hashlib.sha256(payload).hexdigest(),
                    "sampler": document["samplers"][sampler]
                    if sampler is not None
                    else {},
                }
            elif key != "name":
                result[key] = normalize(item)
        return result

    return [
        normalize(document["materials"][p["material"]]) if "material" in p else None
        for p in mesh["primitives"]
    ]


def export_desks(stage, plan):
    combined = None
    nodes = []
    roots = []
    meshes = {}
    materials = {}
    for asset in DESK_IDS:
        source = AUTHORING / f"{asset}.glb"
        with (
            source.open("rb") as stream,
            mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
        ):
            document, start = read_document(data)
            library = Library(document, data, start, stage / "textures")
            if combined is None:
                combined = library
            else:
                library.output = combined.output
                library.buffers = combined.buffers
                library.payload_views = combined.payload_views
                for key in ("extensionsUsed", "extensionsRequired"):
                    if key in document:
                        library.output[key] = sorted(
                            set(library.output.get(key, ())) | set(document[key])
                        )
            children = []
            for record in document["nodes"]:
                if "mesh" not in record:
                    continue
                shape = plan["mesh_at_path"][record["extras"]["v044_path"]]
                if plan["geometry"][shape]["asset"] not in DESK_IDS:
                    continue
                index = record["mesh"]
                signature = material_signature(
                    document, library, document["meshes"][index]
                )
                if shape not in meshes:
                    meshes[shape] = library.mesh(index, shape)
                    materials[shape] = signature
                assert signature == materials[shape], (
                    asset,
                    shape,
                    "desk material changed",
                )
                node = copy.deepcopy(record)
                node["mesh"] = meshes[shape]
                node["extras"]["geometry_id"] = shape
                children.append(len(nodes) + 1)
                nodes.append(node)
            assert len(children) == 9, (asset, children)
            roots.append(len(nodes) + 1)
            nodes.append({"name": "Desk " + asset[-1].upper(), "children": children})
    combined.save(stage / f"{DESK_LIBRARY}.glb", nodes, roots)


def verify_assets(authoring, plan):
    found = {}
    for path in authoring.glob("*.glb"):
        for mesh in glb_meshes(path, defaultdict(set)):
            shape = mesh["shape"]
            assert shape not in found, (path, "duplicate geometry", shape)
            found[shape] = (path.stem, mesh["payload"])
    expected = {
        shape: (
            DESK_LIBRARY if owner["asset"] in DESK_IDS else owner["asset"],
            owner["payload"],
        )
        for shape, owner in plan["geometry"].items()
    }
    assert found == expected, "menu files changed the verified geometry set"


def prepare_menu_assets(candidate, plan):
    candidate = candidate.resolve()
    target = candidate / "menu-authoring"
    if target.exists():
        verify_assets(target, plan)
        return target
    stage = Path(tempfile.mkdtemp(prefix="menu-authoring-", dir=candidate))
    try:
        authoring = candidate / "authoring"
        for path in authoring.glob("*.glb"):
            if path.stem not in DESK_IDS:
                shutil.copyfile(path, stage / path.name)
        shutil.copytree(authoring / "textures", stage / "textures")
        export_desks(stage, plan)
        verify_assets(stage, plan)
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target
