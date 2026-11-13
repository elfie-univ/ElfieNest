"""Strip split display payloads while retaining the validated physical snapshot."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path, PurePosixPath

INPUT_MANIFEST = "nest/assembly/runtime-inputs.json"
SPATIAL_SNAPSHOT = "nest/spatial/estate_spatial.res"
_DISPLAY_EXTENSIONS = {".glb", ".scn", ".tscn", ".png", ".jpg", ".jpeg", ".webp"}
_SOURCE_EXTENSIONS = {
    ".gd",
    ".glb",
    ".scn",
    ".tscn",
    ".tres",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gdshader",
    ".gdshaderinc",
    ".import",
}
_SOURCE_ROOTS = (
    "assembly",
    "buildings",
    "courtyard",
    "furniture",
    "rendering",
    "spatial",
)


def _receipt(payload: bytes) -> dict:
    try:
        data = json.loads(payload)
        files = data["files"]
        if not isinstance(files, dict) or "nest/assembly/estate.tscn" not in files:
            raise ValueError("missing split assembly")
        digest = hashlib.sha256()
        for name, checksum in sorted(files.items()):
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not name.startswith("nest/"):
                raise ValueError("unsafe source path")
            if not isinstance(checksum, str) or not re.fullmatch(
                "[0-9a-f]{64}", checksum
            ):
                raise ValueError("invalid source hash")
            digest.update(f"{name}\t{checksum}\n".encode())
        if data["source_tree"] != digest.hexdigest():
            raise ValueError("source digest differs")
        return data
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid split source receipt: {error}") from error


def verify_split_sources(project: Path) -> dict:
    """Reject stale source receipts before either production export."""
    try:
        receipt = _receipt((project / INPUT_MANIFEST).read_bytes())
    except OSError as error:
        raise ValueError(
            "Missing split source receipt; bake spatial data first"
        ) from error
    actual = {}
    for folder in _SOURCE_ROOTS:
        base = project / "nest" / folder
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in _SOURCE_EXTENSIONS:
                continue
            name = path.relative_to(project).as_posix()
            if name in {INPUT_MANIFEST, SPATIAL_SNAPSHOT}:
                continue
            actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != receipt["files"]:
        changed = sorted(
            set(actual) ^ set(receipt["files"])
            | {
                name
                for name in actual.keys() & receipt["files"].keys()
                if actual[name] != receipt["files"][name]
            }
        )
        raise ValueError(
            "Stale split spatial inputs; rebake: " + ", ".join(changed[:8])
        )
    return receipt


def build_authority_pack(source: Path, destination: Path) -> None:
    """Preserve non-display bytes and the exact source receipt of the full export."""
    with source.open("rb") as original:
        header = original.read(112)
        if len(header) != 112:
            raise ValueError("Truncated Godot PCK header")
        magic, version, _major, _minor, _patch, flags, base, directory = (
            struct.unpack_from("<4sIIIIIQQ", header)
        )
        if magic != b"GDPC" or version != 4 or flags != 2 or base != 112:
            raise ValueError("Unsupported Godot PCK format")
        if not base <= directory < source.stat().st_size:
            raise ValueError("Invalid Godot PCK directory")
        original.seek(directory)
        count = struct.unpack("<I", original.read(4))[0]
        entries = []
        names = set()
        for _ in range(count):
            length = struct.unpack("<I", original.read(4))[0]
            if not 0 < length <= 4096:
                raise ValueError("Invalid Godot PCK path length")
            name = original.read(length).rstrip(b"\0").decode("utf-8")
            offset, size = struct.unpack("<QQ", original.read(16))
            checksum = original.read(16)
            file_flags = struct.unpack("<I", original.read(4))[0]
            if file_flags != 0 or name in names or base + offset + size > directory:
                raise ValueError("Unsupported Godot PCK entry")
            names.add(name)
            entries.append((name, base + offset, size, checksum))
        indexed = {entry[0]: entry for entry in entries}
        if INPUT_MANIFEST not in indexed:
            raise ValueError("Godot PCK is missing its split source receipt")
        if SPATIAL_SNAPSHOT not in indexed:
            raise ValueError("Godot PCK is missing its physical snapshot")
        if any("ElfieNest-complete-final" in name for name in names):
            raise ValueError("Godot PCK contains the retired merged estate")
        _, offset, size, _ = indexed[INPUT_MANIFEST]
        original.seek(offset)
        receipt = _receipt(original.read(size))
        removed = set()
        for name in receipt["files"]:
            if PurePosixPath(name).suffix not in _DISPLAY_EXTENSIONS:
                continue
            for candidate in (name, name + ".remap", name + ".import"):
                if candidate not in indexed:
                    continue
                removed.add(candidate)
                if candidate.endswith((".remap", ".import")):
                    _, offset, size, _ = indexed[candidate]
                    original.seek(offset)
                    for target in re.findall(
                        rb'"res://([^"\r\n]+)"', original.read(size)
                    ):
                        target_name = target.decode()
                        if target_name in names:
                            removed.add(target_name)
        records = []
        with destination.open("wb") as output:
            output.write(header)
            for name, offset, size, checksum in entries:
                if name in removed:
                    continue
                original.seek(offset)
                output.write(bytes((-output.tell()) % 16))
                new_offset = output.tell() - base
                remaining = size
                while remaining:
                    chunk = original.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Truncated Godot PCK payload")
                    output.write(chunk)
                    remaining -= len(chunk)
                records.append((name, new_offset, size, checksum))
            directory = output.tell()
            output.write(struct.pack("<I", len(records)))
            for name, offset, size, checksum in records:
                encoded = name.encode("utf-8")
                encoded += bytes((-len(encoded)) % 4)
                output.write(
                    struct.pack("<I", len(encoded))
                    + encoded
                    + struct.pack("<QQ", offset, size)
                    + checksum
                    + struct.pack("<I", 0)
                )
            output.seek(32)
            output.write(struct.pack("<Q", directory))
