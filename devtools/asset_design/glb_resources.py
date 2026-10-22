"""Read the asset library's content-addressed local GLB dependencies."""

import hashlib
import json
import os
import re
import struct
from pathlib import Path
from typing import Optional, Union

RESOURCE_DIRECTORY = Path("furniture/shared_resources/source/resources")
RESOURCE_NAME = re.compile(r"([0-9a-f]{64})\.(bin|png|jpg)\Z")
IMAGE_MIMES = {".png": "image/png", ".jpg": "image/jpeg"}


def read_glb(path: Union[Path, str]) -> tuple[dict, bytes]:
    raw = Path(path).read_bytes()
    if len(raw) < 20:
        raise ValueError("Truncated GLB header")
    magic, version, total, length, kind = struct.unpack_from("<5I", raw)
    if (magic, version, total, kind) != (0x46546C67, 2, len(raw), 0x4E4F534A):
        raise ValueError("Invalid GLB container")
    end = 20 + length
    if end > len(raw):
        raise ValueError("Truncated GLB JSON")
    doc = json.loads(raw[20:end])
    if end == len(raw):
        return doc, b""
    if end + 8 > len(raw):
        raise ValueError("Truncated GLB binary header")
    size, kind = struct.unpack_from("<2I", raw, end)
    if kind != 0x004E4942 or end + 8 + size != len(raw):
        raise ValueError("Invalid GLB binary chunk")
    return doc, raw[end + 8 :]


def encode_glb(doc: dict, binary: bytes = b"") -> bytes:
    encoded = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += bytes(-len(binary) % 4)
    tail = struct.pack("<II", len(binary), 0x004E4942) + binary if binary else b""
    return (
        struct.pack(
            "<5I",
            0x46546C67,
            2,
            20 + len(encoded) + len(tail),
            len(encoded),
            0x4E4F534A,
        )
        + encoded
        + tail
    )


def resource_path(
    model: Union[Path, str], uri: str, root: Optional[Union[Path, str]] = None
) -> Path:
    """Resolve only ordinary relative paths into the shared resource store."""
    if not isinstance(uri, str) or any(c in uri for c in (":", "\\", "%", "?", "#")):
        raise ValueError("Unapproved external resource URI")
    relative = Path(uri)
    if relative.is_absolute() or not RESOURCE_NAME.fullmatch(relative.name):
        raise ValueError("External resource must use a content-addressed filename")
    model = Path(model).absolute()
    candidate = Path(os.path.abspath(model.parent / relative))
    roots = [Path(root).absolute()] if root is not None else model.parents
    for assets in roots:
        expected = assets / RESOURCE_DIRECTORY / candidate.name
        if candidate != expected or not model.is_relative_to(assets):
            continue
        resolved = candidate.resolve()
        if (
            not resolved.is_relative_to(assets.resolve())
            or resolved.relative_to(assets.resolve())
            != RESOURCE_DIRECTORY / candidate.name
        ):
            raise ValueError("External resource escapes its asset store")
        if not resolved.is_file():
            raise ValueError("External resource unavailable")
        return resolved
    raise ValueError("External resource is outside the shared asset store")


def resource_bytes(
    model: Union[Path, str], uri: str, root: Optional[Union[Path, str]] = None
) -> bytes:
    path = resource_path(model, uri, root)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != path.stem:
        raise ValueError("External resource SHA256 mismatch")
    return data


def dependency_signature(
    model: Union[Path, str], doc: dict, root: Optional[Union[Path, str]] = None
) -> tuple[tuple[str, int, int, int, int], ...]:
    """Include inode/ctime so replacing a payload cannot reuse stale digests."""
    result = []
    for value in doc.get("buffers", []) + doc.get("images", []):
        uri = value.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        path = resource_path(model, uri, root)
        stat = path.stat()
        result.append(
            (str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
        )
    return tuple(result)


def relocate_glb(
    path: Union[Path, str],
    destination: Union[Path, str],
    root: Optional[Union[Path, str]] = None,
) -> bytes:
    """Keep approved dependencies valid when copying a scene to another folder."""
    doc, binary = read_glb(path)
    for value in doc.get("buffers", []) + doc.get("images", []):
        uri = value.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        resource = resource_path(path, uri, root)
        resource_bytes(path, uri, root)
        relocated = Path(
            os.path.relpath(resource, Path(destination).absolute().parent)
        ).as_posix()
        resource_path(destination, relocated, root)
        value["uri"] = relocated
    return encode_glb(doc, binary)
