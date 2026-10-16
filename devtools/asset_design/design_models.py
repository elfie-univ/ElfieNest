"""Read original GLB scene tags and hashes without rewriting saved assets."""

import hashlib
import json
import struct
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def model_info(path: str, modified: int, size: int) -> tuple[list[dict], str]:
    del modified, size
    with Path(path).open("rb") as stream:
        header = stream.read(20)
        if len(header) != 20 or header[:4] != b"glTF" or header[16:20] != b"JSON":
            raise ValueError("Only tagged GLB scenes can be composed")
        length = struct.unpack_from("<I", header, 12)[0]
        if length > 64 * 1024 * 1024:
            raise ValueError("Model scene description is too large")
        data = stream.read(length)
        doc = json.loads(data)
        digest = hashlib.sha256(header + data)
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    records = []

    def visit(index, inherited, ancestry):
        if index in ancestry:
            raise ValueError("Cyclic scene nodes")
        node = doc["nodes"][index]
        properties = {**inherited, **node.get("extras", {})}
        if "mesh" in node:
            records.append({**properties, "node": index, "name": node.get("name", "")})
        for child in node.get("children", []):
            visit(child, properties, {*ancestry, index})

    for index in doc.get("scenes", [{}])[doc.get("scene", 0)].get("nodes", []):
        visit(index, {}, set())
    return records, digest.hexdigest()


def read_model(root: Path, file: str) -> tuple[list[dict], str]:
    path = (root / file).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("Model unavailable")
    stat = path.stat()
    return model_info(str(path), stat.st_mtime_ns, stat.st_size)
