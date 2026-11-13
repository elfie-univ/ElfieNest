"""Build the V044 prototype libraries without modifying either V044 input."""

import copy
import hashlib
import json
import mmap
import shutil
import struct
import tempfile
from collections import defaultdict
from pathlib import Path

from audit_shared_geometry import AUTHORING, BUILD, glb_meshes

CANDIDATE = BUILD / "shared-v044-candidate"
POD = "pod-building"


def read_document(data):
    size = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20 : 20 + size]), 28 + size


class Library:
    """Copy only the geometry and material data used by the chosen prototypes."""

    def __init__(self, source, binary, binary_start, textures, texture_uri="textures"):
        self.source = source
        self.binary = binary
        self.binary_start = binary_start
        self.textures = textures
        self.texture_uri = texture_uri
        self.output = {
            key: source[key]
            for key in ("asset", "extensionsUsed", "extensionsRequired")
            if key in source
        }
        self.buffers = bytearray()
        self.index = {}
        self.payload_views = {}

    def copy_index(self, field, index, transform):
        key = field, index
        if key not in self.index:
            record = transform(copy.deepcopy(self.source[field][index]))
            items = self.output.setdefault(field, [])
            self.index[key] = len(items)
            items.append(record)
        return self.index[key]

    def view_bytes(self, view):
        start = self.binary_start + view.get("byteOffset", 0)
        return self.binary[start : start + view["byteLength"]]

    def view(self, index):
        def relocate(view):
            payload = self.view_bytes(view)
            digest = hashlib.sha256(payload).digest()
            if digest not in self.payload_views:
                self.buffers.extend(b"\0" * (-len(self.buffers) % 4))
                self.payload_views[digest] = len(self.buffers)
                self.buffers.extend(payload)
            view["byteOffset"] = self.payload_views[digest]
            return view

        return self.copy_index("bufferViews", index, relocate)

    def accessor(self, index):
        def relocate(record):
            record["bufferView"] = self.view(record["bufferView"])
            return record

        return self.copy_index("accessors", index, relocate)

    def image(self, index):
        def relocate(record):
            payload = self.view_bytes(
                self.source["bufferViews"][record.pop("bufferView")]
            )
            assert record.pop("mimeType") == "image/png"
            name = hashlib.sha256(payload).hexdigest() + ".png"
            target = self.textures / name
            if not target.exists():
                target.write_bytes(payload)
            record["uri"] = self.texture_uri + "/" + name
            return record

        return self.copy_index("images", index, relocate)

    def texture(self, index):
        def relocate(record):
            record["source"] = self.image(record["source"])
            if "sampler" in record:
                record["sampler"] = self.copy_index(
                    "samplers", record["sampler"], lambda s: s
                )
            return record

        return self.copy_index("textures", index, relocate)

    def material(self, index):
        def relocate(record):
            for key, value in record.items():
                if (
                    key.endswith("Texture")
                    and isinstance(value, dict)
                    and "index" in value
                ):
                    value["index"] = self.texture(value["index"])
                elif isinstance(value, dict):
                    relocate(value)
            return record

        return self.copy_index("materials", index, relocate)

    def mesh(self, index, shape):
        def relocate(record):
            record["name"] = "Geometry_" + shape
            for primitive in record["primitives"]:
                primitive["attributes"] = {
                    key: self.accessor(value)
                    for key, value in primitive["attributes"].items()
                }
                if "indices" in primitive:
                    primitive["indices"] = self.accessor(primitive["indices"])
                if "material" in primitive:
                    primitive["material"] = self.material(primitive["material"])
                for target in primitive.get("targets", []):
                    target.update(
                        {key: self.accessor(value) for key, value in target.items()}
                    )
            return record

        return self.copy_index("meshes", index, relocate)

    def save(self, path, nodes, roots=None, variants=()):
        self.output["nodes"] = [
            {
                "name": path.stem,
                "children": roots
                if roots is not None
                else list(range(1, len(nodes) + 1)),
            },
            *nodes,
        ]
        self.output["scenes"] = [{"nodes": [0]}, *variants]
        self.output["scene"] = 0
        self.buffers.extend(b"\0" * (-len(self.buffers) % 4))
        self.output["buffers"] = [{"byteLength": len(self.buffers)}]
        data = json.dumps(self.output, separators=(",", ":")).encode()
        data += b" " * (-len(data) % 4)
        with path.open("wb") as output:
            output.write(
                struct.pack(
                    "<4sIIII",
                    b"glTF",
                    2,
                    28 + len(data) + len(self.buffers),
                    len(data),
                    0x4E4F534A,
                )
            )
            output.write(data)
            output.write(struct.pack("<II", len(self.buffers), 0x004E4942))
            output.write(self.buffers)


def representative_groups(items, source_shapes, inventory):
    result = {}
    for item in items:
        asset = item["id"]
        if not asset.startswith("common-") and asset not in (
            "plant-library",
            "forest-library",
        ):
            continue
        placements = defaultdict(list)
        for path in item["paths"]:
            if path not in source_shapes:
                continue
            extras = inventory[path]["extras"]
            key = (
                extras.get("module"),
                extras.get("resident"),
                extras.get("designTemplateInstance", path),
            )
            placements[key].append(path)
        chosen = {}
        for paths in placements.values():
            signature = tuple(sorted(source_shapes[path] for path in paths))
            chosen.setdefault(signature, paths)
        result[asset] = list(chosen.values())
    return result


def owner_rank(asset):
    if asset == POD:
        return 0
    if asset in ("bed", "chair") or asset.startswith("common-"):
        return 1
    if asset in ("forest-library", "plant-library", "tree-one"):
        return 2
    if asset.startswith("desk-"):
        return 3
    if asset == "retained-placement-variants":
        return 9
    return 4


def compile_sources(stage):
    bindings = json.loads((BUILD / "static-export-bindings.json").read_text())
    inventory = {
        n["path"]: n
        for n in json.loads((BUILD / "full-inventory/static-nodes.json").read_text())
    }
    authored = sorted(
        AUTHORING.glob("*.glb"), key=lambda p: (owner_rank(p.stem), p.name)
    )
    geometry = {}
    source_shapes = {}
    by_asset = {}
    for path in authored:
        records = glb_meshes(path, defaultdict(set))
        by_asset[path.stem] = records
        for record in records:
            shape = record["shape"]
            owner = geometry.setdefault(
                shape,
                {
                    "asset": path.stem,
                    "original_mesh": record["mesh"],
                    "payload": record["payload"],
                    "source_path": record["placements"][0],
                },
            )
            assert owner["payload"] == record["payload"], (path, shape)
            for node_path in record["placements"]:
                assert source_shapes.setdefault(node_path, shape) == shape, node_path

    pod_groups = defaultdict(dict)
    for record in by_asset[POD]:
        for path in record["placements"]:
            module = inventory[path]["extras"]["module"]
            assert record["shape"] not in pod_groups[module], path
            pod_groups[module][record["shape"]] = path
    assert sorted(pod_groups) == [f"M{i:02}" for i in range(1, 9)]
    assert len(pod_groups["M01"]) == 53
    assert all(
        paths.keys() == pod_groups["M01"].keys() for paths in pod_groups.values()
    )
    for shape, path in pod_groups["M01"].items():
        record = next(item for item in by_asset[POD] if path in item["placements"])
        geometry[shape].update(source_path=path, original_mesh=record["mesh"])

    groups = representative_groups(bindings["items"], source_shapes, inventory)
    for asset, representatives in groups.items():
        by_path = {
            path: record for record in by_asset[asset] for path in record["placements"]
        }
        chosen = set()
        for path in (p for group in representatives for p in group):
            shape = source_shapes[path]
            owner = geometry[shape]
            if owner["asset"] == asset and shape not in chosen:
                owner.update(source_path=path, original_mesh=by_path[path]["mesh"])
                chosen.add(shape)
        assert chosen == {
            shape for shape, owner in geometry.items() if owner["asset"] == asset
        }, asset
    authoring = stage / "authoring"
    textures = authoring / "textures"
    textures.mkdir(parents=True)
    counts = {}
    for path in authored:
        asset = path.stem
        if not any(record["asset"] == asset for record in geometry.values()):
            continue
        with (
            path.open("rb") as stream,
            mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as binary,
        ):
            document, start = read_document(binary)
            library = Library(document, binary, start, textures)
            allowed = None
            if asset == POD:
                allowed = set(pod_groups["M01"].values())
            elif asset in groups:
                allowed = {p for group in groups[asset] for p in group}
            seen = set()
            nodes = []
            for node in document["nodes"]:
                if "mesh" not in node:
                    continue
                node_path = node["extras"]["v044_path"]
                shape = source_shapes[node_path]
                owner = geometry[shape]
                if owner["asset"] != asset:
                    continue
                if allowed is not None and node_path not in allowed:
                    continue
                if asset == "retained-placement-variants" and shape in seen:
                    continue
                mesh = library.mesh(owner["original_mesh"], shape)
                owner["mesh"] = mesh
                node = copy.deepcopy(node)
                node["mesh"] = mesh
                node["extras"]["geometry_id"] = shape
                nodes.append(node)
                seen.add(shape)
            library.save(authoring / path.name, nodes)
            counts[asset] = {"meshes": len(seen), "nodes": len(nodes)}

    exported = {}
    for path in authoring.glob("*.glb"):
        for record in glb_meshes(path, defaultdict(set)):
            assert record["shape"] not in exported, (path, record["shape"])
            exported[record["shape"]] = (path.stem, record["mesh"], record["payload"])
    assert exported == {
        shape: (record["asset"], record["mesh"], record["payload"])
        for shape, record in geometry.items()
    }
    plan = {
        "snapshot_sha256": bindings["snapshot_sha256"],
        "geometry": geometry,
        "mesh_at_path": source_shapes,
        "views": bindings["items"],
        "showcase_groups": groups,
        "pod_parts": dict(sorted(pod_groups.items())),
        "authoring_libraries": counts,
        "unique_geometry": len(geometry),
        "duplicate_mesh_records": 0,
        "glb_bytes": sum(p.stat().st_size for p in authoring.glob("*.glb")),
        "texture_files": len(list(textures.iterdir())),
        "texture_bytes": sum(p.stat().st_size for p in textures.iterdir()),
    }
    (stage / "assembly-plan.json").write_text(json.dumps(plan, ensure_ascii=False))
    print(
        {
            k: plan[k]
            for k in (
                "unique_geometry",
                "duplicate_mesh_records",
                "glb_bytes",
                "texture_files",
                "texture_bytes",
            )
        }
    )


def main():
    if CANDIDATE.exists():
        raise FileExistsError(
            f"Preserve the existing candidate before rebuilding: {CANDIDATE}"
        )
    stage = Path(tempfile.mkdtemp(prefix="shared-v044-", dir=BUILD))
    try:
        compile_sources(stage)
        stage.rename(CANDIDATE)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    main()
