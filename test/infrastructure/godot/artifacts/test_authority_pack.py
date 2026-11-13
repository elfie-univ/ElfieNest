"""Physical-only packaging retains every other byte and proves input identity."""

import hashlib
import json
import struct
from pathlib import Path

import pytest

from infrastructure.godot.artifacts.authority_pack import (
    build_authority_pack,
    verify_split_sources,
)


def make_pack(path: Path, files: dict[str, bytes]) -> None:
    with path.open("wb") as stream:
        stream.write(struct.pack("<4sIIIIIQQ", b"GDPC", 4, 4, 7, 0, 2, 112, 0))
        stream.write(bytes(72))
        records = []
        for name, payload in files.items():
            offset = stream.tell() - 112
            stream.write(payload)
            encoded = name.encode()
            records.append(
                struct.pack("<I", len(encoded))
                + encoded
                + struct.pack("<QQ", offset, len(payload))
                + hashlib.md5(payload).digest()
                + struct.pack("<I", 0)
            )
        directory = stream.tell()
        stream.write(struct.pack("<I", len(records)))
        for record in records:
            stream.write(record)
        stream.seek(32)
        stream.write(struct.pack("<Q", directory))


def read_pack(path: Path) -> dict[str, bytes]:
    with path.open("rb") as stream:
        header = stream.read(40)
        base, directory = struct.unpack_from("<QQ", header, 24)
        stream.seek(directory)
        count = struct.unpack("<I", stream.read(4))[0]
        entries = []
        for _ in range(count):
            size = struct.unpack("<I", stream.read(4))[0]
            name = stream.read(size).rstrip(b"\0").decode()
            offset, length = struct.unpack("<QQ", stream.read(16))
            stream.read(20)
            entries.append((name, base + offset, length))
        result = {}
        for name, offset, length in entries:
            stream.seek(offset)
            result[name] = stream.read(length)
        return result


def test_authority_pack_preserves_payloads_and_input_hashes(tmp_path: Path) -> None:
    scene = ".godot/imported/central-building.glb-test.scn"
    source_files = {
        "nest/assembly/estate.tscn": hashlib.sha256(b"split assembly").hexdigest(),
        "nest/buildings/main/central-building.glb": hashlib.sha256(
            b"split prototype"
        ).hexdigest(),
    }
    digest = hashlib.sha256()
    for name, value in sorted(source_files.items()):
        digest.update(f"{name}\t{value}\n".encode())
    receipt = json.dumps(
        {"source_tree": digest.hexdigest(), "files": source_files}
    ).encode()
    files = {
        scene: b"complete display model" * 30,
        "nest/buildings/main/central-building.glb.remap": f'[remap]\npath="res://{scene}"'.encode(),
        "nest/assembly/estate.tscn": b"split assembly",
        "nest/assembly/runtime-inputs.json": receipt,
        "nest/spatial/estate_spatial.res": b"all physical shapes and navigation",
        "characters/resident.scn": b"complete resident model",
        "project.binary": b"project settings",
    }
    original = tmp_path / "full.pck"
    output = tmp_path / "authority.pck"
    make_pack(original, files)
    before = original.read_bytes()
    build_authority_pack(original, output)
    packed = read_pack(output)
    assert packed["nest/assembly/runtime-inputs.json"] == receipt
    removed = {
        scene,
        "nest/buildings/main/central-building.glb.remap",
        "nest/assembly/estate.tscn",
    }
    assert packed == {
        name: payload for name, payload in files.items() if name not in removed
    }
    assert original.read_bytes() == before


def test_authority_pack_rejects_unrecognized_pack(tmp_path: Path) -> None:
    original = tmp_path / "full.pck"
    original.write_bytes(bytes(112))
    with pytest.raises(ValueError, match="PCK"):
        build_authority_pack(original, tmp_path / "authority.pck")


def test_authority_pack_rejects_missing_split_receipt(tmp_path: Path) -> None:
    original = tmp_path / "full.pck"
    make_pack(original, {"nest/spatial/estate_spatial.res": b"physical world"})
    with pytest.raises(ValueError, match="receipt"):
        build_authority_pack(original, tmp_path / "authority.pck")


def test_source_receipt_rejects_changed_and_new_split_inputs(tmp_path: Path) -> None:
    assembly = tmp_path / "nest/assembly"
    assembly.mkdir(parents=True)
    scene = assembly / "estate.tscn"
    scene.write_bytes(b"split world")
    name = "nest/assembly/estate.tscn"
    checksum = hashlib.sha256(scene.read_bytes()).hexdigest()
    receipt = {
        "files": {name: checksum},
        "source_tree": hashlib.sha256(f"{name}\t{checksum}\n".encode()).hexdigest(),
    }
    (assembly / "runtime-inputs.json").write_text(json.dumps(receipt))
    assert verify_split_sources(tmp_path) == receipt
    scene.write_bytes(b"edited split world")
    with pytest.raises(ValueError, match="Stale split"):
        verify_split_sources(tmp_path)
    scene.write_bytes(b"split world")
    (assembly / "new.tres").write_bytes(b"new activity data")
    with pytest.raises(ValueError, match="new.tres"):
        verify_split_sources(tmp_path)
