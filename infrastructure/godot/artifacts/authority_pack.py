"""Build a smaller authority package without changing the complete observer pack."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

_INPUTS = {
    "instances": "rooms/estate/ElfieNest-complete-final.instances.bin",
    "lighting": "rooms/estate/estate_outdoor_lighting.scn",
}
INPUT_MANIFEST = "rooms/estate/authority_inputs.json"


def build_authority_pack(source: Path, destination: Path) -> None:
    """Keep every exported file except the unused display scene; record its hash.

    Only Godot's pinned, unencrypted standalone V4 format is supported. Input
    hashes come from the complete export, so the physical snapshot still fails
    closed when any authoring input changes without a matching spatial bake.
    """
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
        names: set[str] = set()
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
        scenes = [
            name
            for name in names
            if name.startswith(".godot/imported/ElfieNest-complete-final.glb-")
            and name.endswith(".scn")
        ]
        if (
            len(scenes) != 1
            or not set(_INPUTS.values()) <= names
            or INPUT_MANIFEST in names
        ):
            raise ValueError(
                "Godot PCK must contain exactly one complete estate and its inputs"
            )
        inputs = {**_INPUTS, "scene": scenes[0]}
        digests: dict[str, str] = {}
        records = []
        with destination.open("wb") as output:
            output.write(header)
            for name, offset, size, checksum in entries:
                original.seek(offset)
                output.write(bytes((-output.tell()) % 16))
                new_offset = output.tell() - base
                digest = hashlib.sha256() if name in inputs.values() else None
                remaining = size
                while remaining:
                    chunk = original.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Truncated Godot PCK payload")
                    if digest is not None:
                        digest.update(chunk)
                    if name != scenes[0]:
                        output.write(chunk)
                    remaining -= len(chunk)
                if digest is not None:
                    digests[name] = digest.hexdigest()
                if name != scenes[0]:
                    records.append((name, new_offset, size, checksum))
            payload = json.dumps(
                {key: digests[name] for key, name in inputs.items()}, sort_keys=True
            ).encode("utf-8")
            output.write(bytes((-output.tell()) % 16))
            records.append(
                (
                    INPUT_MANIFEST,
                    output.tell() - base,
                    len(payload),
                    hashlib.md5(payload).digest(),
                )
            )
            output.write(payload)
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
