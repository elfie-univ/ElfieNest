"""Convert the estate's affine matrices to exact Godot MultiMesh buffers."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

ORDER = (0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14)


def compact(data: bytes) -> bytes:
    """Drop only the verified constant row, preserving every float's bits."""
    magic, version, groups, total = struct.unpack_from("<8sIII", data)
    if magic != b"ENINST01" or version != 1:
        raise ValueError("Expected the original estate instance format")
    output = bytearray(struct.pack("<8sIII", magic, 2, groups, total))
    cursor = 20
    observed = 0
    for _ in range(groups):
        length, count = struct.unpack_from("<II", data, cursor)
        end = cursor + 8 + length
        if not 0 < length <= 256 or end + count * 64 > len(data):
            raise ValueError("Truncated instance group")
        output.extend(data[cursor:end])
        cursor = end
        for _ in range(count):
            matrix = data[cursor : cursor + 64]
            if any(
                struct.unpack_from("<f", matrix, index * 4)[0] != expected
                for index, expected in ((3, 0), (7, 0), (11, 0), (15, 1))
            ):
                raise ValueError("Non-affine matrix cannot be compacted")
            for index in ORDER:
                output.extend(matrix[index * 4 : index * 4 + 4])
            cursor += 64
        observed += count
    if cursor != len(data) or observed != total:
        raise ValueError("Instance count or trailing data mismatch")
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = compact(args.source.read_bytes())
    with args.output.open("xb") as output:
        output.write(payload)


if __name__ == "__main__":
    main()
