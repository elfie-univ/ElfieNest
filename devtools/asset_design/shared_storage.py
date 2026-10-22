"""Store unchanged mesh packets and encoded images once across design assets."""

import copy
import hashlib
import os
from pathlib import Path

from devtools.asset_design.glb_resources import (
    RESOURCE_DIRECTORY,
    encode_glb,
    read_glb,
    resource_bytes,
)


def externalize_glb(source: Path, target: Path, root: Path) -> list[Path]:
    """Keep scene/node/material semantics; replace payload storage with local URIs."""
    source, target, root = source.resolve(), target.resolve(), root.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Shared model must remain inside the asset workspace")
    doc, binary = read_glb(source)
    if doc.get("animations") or doc.get("skins") or doc.get("extensionsRequired"):
        raise ValueError("Shared storage requires reviewed static GLB assets")
    output = copy.deepcopy(doc)
    views: list[dict] = []
    accessors: list[dict] = []
    buffers: list[dict] = []
    resources: dict[str, Path] = {}
    buffer_ids: dict[str, int] = {}

    def original_buffer(index: int) -> bytes:
        descriptor = doc["buffers"][index]
        if "uri" in descriptor:
            return resource_bytes(source, descriptor["uri"], root)
        if index != 0:
            raise ValueError("Only buffer zero can use the GLB binary chunk")
        return binary

    def original_view(index: int) -> bytes:
        view = doc["bufferViews"][index]
        start = view.get("byteOffset", 0)
        data = original_buffer(view.get("buffer", 0))[
            start : start + view["byteLength"]
        ]
        if len(data) != view["byteLength"]:
            raise ValueError("Truncated shared storage input")
        return data

    def store(data: bytes, suffix: str) -> str:
        filename = hashlib.sha256(data).hexdigest() + suffix
        path = root / RESOURCE_DIRECTORY / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError("Existing content-addressed resource changed")
        else:
            with path.open("xb") as stream:
                stream.write(data)
        resources[filename] = path
        return Path(os.path.relpath(path, target.parent)).as_posix()

    def packet(mesh: dict) -> None:
        payload = bytearray()
        accessor_map: dict[int, int] = {}
        view_map: dict[int, int] = {}
        packet_views: list[int] = []

        def accessor(index: int) -> int:
            if index in accessor_map:
                return accessor_map[index]
            value = copy.deepcopy(doc["accessors"][index])
            if value.get("sparse") or value.get("extensions"):
                raise ValueError("Sparse or extended accessor requires review")
            old_view = value.get("bufferView")
            if old_view is not None:
                if old_view not in view_map:
                    view = copy.deepcopy(doc["bufferViews"][old_view])
                    if view.get("extensions"):
                        raise ValueError("Extended buffer view requires review")
                    payload.extend(bytes(-len(payload) % 4))
                    view["byteOffset"] = len(payload)
                    payload.extend(original_view(old_view))
                    view_map[old_view] = len(views)
                    packet_views.append(len(views))
                    views.append(view)
                value["bufferView"] = view_map[old_view]
            accessor_map[index] = len(accessors)
            accessors.append(value)
            return accessor_map[index]

        for primitive in mesh["primitives"]:
            if primitive.get("extensions"):
                raise ValueError("Extended primitive requires review")
            primitive["attributes"] = {
                name: accessor(primitive["attributes"][name])
                for name in sorted(primitive["attributes"])
            }
            if "indices" in primitive:
                primitive["indices"] = accessor(primitive["indices"])
            if primitive.get("targets"):
                primitive["targets"] = [
                    {name: accessor(index) for name, index in target.items()}
                    for target in primitive["targets"]
                ]
        if payload:
            uri = store(bytes(payload), ".bin")
            if uri not in buffer_ids:
                buffer_ids[uri] = len(buffers)
                buffers.append({"uri": uri, "byteLength": len(payload)})
            for index in packet_views:
                views[index]["buffer"] = buffer_ids[uri]

    for mesh in output.get("meshes", []):
        packet(mesh)
    for image in output.get("images", []):
        if "bufferView" in image:
            data = original_view(image.pop("bufferView"))
        elif image.get("uri"):
            data = resource_bytes(source, image["uri"], root)
        else:
            raise ValueError("Shared image payload unavailable")
        suffix = {"image/png": ".png", "image/jpeg": ".jpg"}.get(image["mimeType"])
        if suffix is None:
            raise ValueError("Shared image encoding requires review")
        image["uri"] = store(data, suffix)
    output.update(buffers=buffers, bufferViews=views, accessors=accessors)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encode_glb(output))
    return list(resources.values())
