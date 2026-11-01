"""Exact affine compaction must not quantize transforms or accept corruption."""

import struct

import pytest

from scripts.internal.build.compact_estate_instances import compact


def source(matrix: list[float]) -> bytes:
    return (
        struct.pack("<8sIII", b"ENINST01", 1, 1, 1)
        + struct.pack("<II", 4, 1)
        + b"tree"
        + struct.pack("<16f", *matrix)
    )


def test_affine_transform_keeps_exact_float_payload() -> None:
    matrix = [
        1.0,
        2.0,
        3.0,
        0.0,
        4.0,
        5.0,
        6.0,
        0.0,
        7.0,
        8.0,
        9.0,
        0.0,
        -0.0,
        100.25,
        -42.125,
        1.0,
    ]
    original = source(matrix)
    result = compact(original)
    assert result[:8] == original[:8]
    assert struct.unpack_from("<I", result, 8)[0] == 2
    assert result[12:32] == original[12:32]
    assert len(result) == len(original) - 16
    for target, old in enumerate((0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14)):
        assert (
            result[32 + target * 4 : 36 + target * 4]
            == original[32 + old * 4 : 36 + old * 4]
        )


def test_reject_non_affine_or_incomplete_data() -> None:
    matrix = [0.0] * 16
    matrix[15] = 1.0
    with pytest.raises(ValueError, match="Truncated"):
        compact(source(matrix)[:-1])
    with pytest.raises(ValueError, match="trailing"):
        compact(source(matrix) + b"extra")
    matrix[3] = 0.5
    with pytest.raises(ValueError, match="Non-affine"):
        compact(source(matrix))
