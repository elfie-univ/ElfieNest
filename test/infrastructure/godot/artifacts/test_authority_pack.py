"""Physical-only packaging retains every other byte and proves input identity."""

import hashlib
import json
import struct
from pathlib import Path

import pytest

from infrastructure.godot.artifacts.authority_pack import build_authority_pack


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
    scene = ".godot/imported/ElfieNest-complete-final.glb-test.scn"
    files = {
        scene: b"complete display model" * 30,
        "rooms/estate/ElfieNest-complete-final.instances.bin": b"instances",
        "rooms/estate/estate_outdoor_lighting.scn": b"lighting",
        "rooms/estate/estate_spatial.res": b"all physical shapes and navigation",
        "characters/resident.scn": b"complete resident model",
        "project.binary": b"project settings",
    }
    original = tmp_path / "full.pck"
    output = tmp_path / "authority.pck"
    make_pack(original, files)
    before = original.read_bytes()
    build_authority_pack(original, output)
    packed = read_pack(output)
    inputs = json.loads(packed.pop("rooms/estate/authority_inputs.json"))
    assert inputs == {
        "scene": hashlib.sha256(files[scene]).hexdigest(),
        "instances": hashlib.sha256(b"instances").hexdigest(),
        "lighting": hashlib.sha256(b"lighting").hexdigest(),
    }
    assert packed == {name: payload for name, payload in files.items() if name != scene}
    assert original.read_bytes() == before


def test_authority_pack_rejects_unrecognized_pack(tmp_path: Path) -> None:
    original = tmp_path / "full.pck"
    original.write_bytes(bytes(112))
    with pytest.raises(ValueError, match="PCK"):
        build_authority_pack(original, tmp_path / "authority.pck")
