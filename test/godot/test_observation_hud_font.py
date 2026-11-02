"""Verify the shipped HUD font without Godot, system fonts or font dependencies."""

import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "godot_project"
FONT = ROOT / "ui/fonts/NotoSansSC-ObservationHUD.ttf"
HUD = ROOT / "ui/observation_hud.tscn"


def _tables(data: bytes) -> dict[bytes, tuple[int, int]]:
    assert data[:4] == b"\0\1\0\0", "Font must be a real standalone TrueType file"
    count = struct.unpack_from(">H", data, 4)[0]
    return {
        tag: (offset, length)
        for tag, _checksum, offset, length in (
            struct.unpack_from(">4sIII", data, 12 + index * 16)
            for index in range(count)
        )
    }


def _glyph_id(data: bytes, tables: dict[bytes, tuple[int, int]], code: int) -> int:
    offset, _length = tables[b"cmap"]
    count = struct.unpack_from(">H", data, offset + 2)[0]
    for index in range(count):
        platform, encoding, relative = struct.unpack_from(
            ">HHI", data, offset + 4 + 8 * index
        )
        if platform != 0 and (platform, encoding) not in {(3, 1), (3, 10)}:
            continue
        table = offset + relative
        format_id = struct.unpack_from(">H", data, table)[0]
        if format_id == 12:
            groups = struct.unpack_from(">I", data, table + 12)[0]
            for group in range(groups):
                start, end, glyph = struct.unpack_from(
                    ">III", data, table + 16 + 12 * group
                )
                if start <= code <= end:
                    return glyph + code - start
        elif format_id == 4 and code <= 0xFFFF:
            segments = struct.unpack_from(">H", data, table + 6)[0] // 2
            ends = table + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            ranges = deltas + 2 * segments
            for segment in range(segments):
                start = struct.unpack_from(">H", data, starts + 2 * segment)[0]
                end = struct.unpack_from(">H", data, ends + 2 * segment)[0]
                if start <= code <= end:
                    delta = struct.unpack_from(">h", data, deltas + 2 * segment)[0]
                    address = ranges + 2 * segment
                    relative_glyph = struct.unpack_from(">H", data, address)[0]
                    if not relative_glyph:
                        return (code + delta) & 0xFFFF
                    glyph = struct.unpack_from(
                        ">H", data, address + relative_glyph + 2 * (code - start)
                    )[0]
                    return (glyph + delta) & 0xFFFF if glyph else 0
    return 0


def test_shipped_font_covers_current_hud_and_camera_labels_with_real_outlines() -> None:
    data = FONT.read_bytes()
    tables = _tables(data)
    text = "".join(
        (ROOT / path).read_text()
        for path in (
            "ui/observation_hud.tscn",
            "ui/observation_hud.gd",
            "rooms/nest.gd",
        )
    )
    required = set(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    required.update(chr(value) for value in range(33, 127))
    required.add("·")
    assert required
    head, _ = tables[b"head"]
    long_offsets = struct.unpack_from(">h", data, head + 50)[0]
    loca, _ = tables[b"loca"]
    for character in sorted(required):
        glyph = _glyph_id(data, tables, ord(character))
        assert glyph > 0, f"Missing HUD glyph: {character} U+{ord(character):04X}"
        width, format_id = (4, ">II") if long_offsets else (2, ">HH")
        start, end = struct.unpack_from(format_id, data, loca + glyph * width)
        assert end > start, f"HUD glyph has no outline: {character}"
    assert len(data) < 256 * 1024, "HUD subset unexpectedly became a full CJK font"


def test_hud_theme_binds_real_font_for_controls_popup_and_tooltips() -> None:
    source = HUD.read_text()
    assert (
        '[ext_resource type="FontFile" path="res://ui/fonts/NotoSansSC-ObservationHUD.ttf" id="2_font"]'
        in source
    )
    assert 'default_font = ExtResource("2_font")' in source
    for control in ("Label", "Button", "OptionButton", "PopupMenu", "TooltipLabel"):
        assert f'{control}/fonts/font = ExtResource("2_font")' in source
    margin = source.split('[node name="Margin"', 1)[1].split("[node ", 1)[0]
    assert 'theme = SubResource("Theme_hud")' in margin
    assert "SystemFont" not in source


def test_font_license_is_present_and_referenced_for_export() -> None:
    license_text = (ROOT / "ui/fonts/OFL.txt").read_text()
    assert "SIL OPEN FONT LICENSE Version 1.1" in license_text
    assert "Copyright 2014-2021 Adobe" in license_text
    # The Theme references this resource so exported PCKs retain the license.
    license_resource = (ROOT / "ui/fonts/OFL.tres").read_text()
    embedded_license = re.search(
        r'^metadata/license_text = (".*")$', license_resource, re.MULTILINE
    )
    assert embedded_license is not None
    assert json.loads(embedded_license.group(1)) == license_text
    assert 'path="res://ui/fonts/OFL.tres"' in HUD.read_text()
    assert 'metadata/font_license = ExtResource("3_font_license")' in HUD.read_text()
