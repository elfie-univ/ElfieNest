"""Measure the files and shared geometry behind the Nest Lab review panel."""

import mmap
from collections import defaultdict
from functools import cache
from urllib.parse import unquote

from export_shared_asset_sources import read_document


def merged_ranges(ranges):
    merged = []
    for buffer, start, end in sorted(ranges):
        if merged and buffer == merged[-1][0] and start <= merged[-1][2]:
            _, first, previous_end = merged[-1]
            merged[-1] = buffer, first, max(previous_end, end)
        else:
            merged.append((buffer, start, end))
    return tuple(merged)


def range_bytes(ranges):
    return sum(end - start for _, start, end in merged_ranges(ranges))


def texture_indices(material):
    for name, value in material.items():
        if not isinstance(value, dict):
            continue
        if name.endswith("Texture") and "index" in value:
            yield value["index"]
        else:
            yield from texture_indices(value)


def glb_resources(path, components, file_bytes):
    with (
        path.open("rb") as stream,
        mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
    ):
        document, _ = read_document(data)

    images = document.get("images", [])
    external = {
        index: (path.parent / unquote(image["uri"])).resolve()
        for index, image in enumerate(images)
        if "uri" in image and not image["uri"].startswith("data:")
    }
    dependencies = set(external.values())

    def view_range(index):
        view = document["bufferViews"][index]
        start = view.get("byteOffset", 0)
        return view["buffer"], start, start + view["byteLength"]

    @cache
    def mesh_ranges(mesh):
        accessors = set()
        for primitive in document["meshes"][mesh]["primitives"]:
            accessors.update(primitive["attributes"].values())
            if "indices" in primitive:
                accessors.add(primitive["indices"])
            for target in primitive.get("targets", []):
                accessors.update(target.values())
        return {
            view_range(document["accessors"][index]["bufferView"])
            for index in accessors
        }

    @cache
    def mesh_images(mesh):
        return {
            document["textures"][texture]["source"]
            for primitive in document["meshes"][mesh]["primitives"]
            if "material" in primitive
            for texture in texture_indices(document["materials"][primitive["material"]])
        }

    nodes = document["nodes"]

    def meshes_below(index):
        node = nodes[index]
        if "mesh" in node:
            yield node["mesh"]
        for child in node.get("children", []):
            yield from meshes_below(child)

    groups = defaultdict(list)
    component_ids = {component["id"] for component in components}
    source_meshes = defaultdict(set)
    for index, node in enumerate(nodes):
        extras = node.get("extras", {})
        key = extras.get("component_id")
        if (
            key in component_ids
            and "mesh" not in node
            and node.get("children")
            and not extras.get("nest_instance_group")
        ):
            groups[key].append(set(meshes_below(index)))
        if extras.get("v044_path"):
            source_meshes[extras["v044_path"]].update(meshes_below(index))

    listed = set()
    for component in components:
        instances = groups[component["id"]]
        if "instanceSize" in component:
            # One placement may have multiple meshes (door, lining, and light).
            # Read the declared placements from existing paths without
            # restructuring or duplicating the library's runtime mesh nodes.
            width = component["instanceSize"]
            paths = component["paths"]
            assert type(width) is int and width > 0, component["id"]
            assert len(paths) == len(set(paths)) == width * component["count"], (
                component["id"]
            )
            assert all(path in source_meshes for path in paths), component["id"]
            instances = [
                set().union(*(source_meshes[path] for path in paths[i : i + width]))
                for i in range(0, len(paths), width)
            ]
        if not instances:
            continue  # Older exports have selection paths but no authored group nodes.
        geometry = {
            merged_ranges(set().union(*(mesh_ranges(mesh) for mesh in meshes)))
            for meshes in instances
        }
        geometry_ranges = merged_ranges(
            {span for layout in geometry for span in layout}
        )
        listed.update(geometry_ranges)
        textures = set().union(
            *(mesh_images(mesh) for meshes in instances for mesh in meshes)
        )
        image_ranges = merged_ranges(
            {
                view_range(images[index]["bufferView"])
                for index in textures
                if "bufferView" in images[index]
            }
        )
        texture_files = {external[index] for index in textures if index in external}
        inline_bytes = sum(
            len(images[index]["uri"])
            for index in textures
            if images[index].get("uri", "").startswith("data:")
        )
        component["size"] = {
            "meshBytes": sum(end - start for _, start, end in geometry_ranges),
            "textureBytes": sum(end - start for _, start, end in image_ranges)
            + sum(file_bytes(file) for file in texture_files)
            + inline_bytes,
            "instances": len(instances),
            "meshCopies": len(geometry),
        }
    ordinary = {
        span
        for node in nodes
        if "mesh" in node and "normal_variant_of" not in node.get("extras", {})
        for span in mesh_ranges(node["mesh"])
    }
    variants = {
        span
        for node in nodes
        if "mesh" in node and "normal_variant_of" in node.get("extras", {})
        for span in mesh_ranges(node["mesh"])
    }
    embedded = {
        view_range(image["bufferView"]) for image in images if "bufferView" in image
    }
    listed_bytes = range_bytes(listed)
    ordinary_bytes = range_bytes(listed | ordinary)
    mesh_bytes = range_bytes(listed | ordinary | variants)
    payload_bytes = range_bytes(listed | ordinary | variants | embedded)
    return dependencies, {
        "componentMeshBytes": listed_bytes,
        "otherMeshBytes": ordinary_bytes - listed_bytes,
        "variantMeshBytes": mesh_bytes - ordinary_bytes,
        "embeddedTextureBytes": payload_bytes - mesh_bytes,
        "otherFileBytes": file_bytes(path) - payload_bytes,
    }


def add_asset_sizes(entries, assets):
    assets = assets.resolve()

    @cache
    def file_bytes(path):
        path.relative_to(assets)
        return path.stat().st_size

    files = {key: (assets / entry["file"]).resolve() for key, entry in entries.items()}
    file_titles = {files[key]: entry["title"] for key, entry in entries.items()}
    resources = {}
    breakdowns = {}
    for key, entry in entries.items():
        path = files[key]
        resources[key] = {path}
        if path.suffix == ".glb":
            textures, breakdown = glb_resources(
                path, entry.get("components", []), file_bytes
            )
            resources[key].update(textures)
            if breakdown:
                breakdowns[key] = breakdown

    for key, entry in entries.items():
        found = set()
        pending = [key]
        included = set()
        while pending:
            asset = pending.pop()
            if asset in found:
                continue
            found.add(asset)
            included.update(resources[asset])
            pending.extend(row["id"] for row in entries[asset].get("parts", []))
            pending.extend(entries[asset].get("members", []))
        included.remove(files[key])
        entry["size"] = {
            "fileBytes": file_bytes(files[key]),
            "referenceBytes": sum(file_bytes(path) for path in included),
        }
        if included:
            entry["size"]["referenceFiles"] = [
                {
                    "path": path.relative_to(assets).as_posix(),
                    "title": file_titles.get(path, path.name),
                    "bytes": file_bytes(path),
                }
                for path in sorted(included, key=lambda path: (-file_bytes(path), path))
            ]
        if key in breakdowns:
            entry["size"]["breakdown"] = breakdowns[key]
