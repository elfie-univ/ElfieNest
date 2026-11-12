"""Prepare a plant-library candidate; preserve detail and verify PNG pixels exactly.

Run with the repository Python as a module. Outputs and measurements stay in build/.
The current GLB remains the source; this tool does not overwrite it.
"""

import argparse
import copy
import hashlib
import io
import json
import struct
from pathlib import Path

from PIL import Image, PngImagePlugin

from scripts.internal.build.optimize_estate_glb import share_resources

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "godot_project/nest/furniture/shared/main/main-planters.glb"
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
FORMATS = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}


def load(path):
    raw = path.read_bytes()
    assert struct.unpack_from("<III", raw) == (0x46546C67, 2, len(raw))
    length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20 : 20 + length])
    binary = raw[28 + length :]
    assert not doc.get("animations") and not doc.get("skins")
    arrays = []
    for a in doc["accessors"]:
        assert not a.get("sparse") and not a.get("extensions")
        view = doc["bufferViews"][a["bufferView"]]
        fmt = "<" + FORMATS[a["componentType"]] * WIDTHS[a["type"]]
        size = struct.calcsize(fmt)
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = view.get("byteStride", size)
        arrays.append(
            b"".join(
                binary[start + i * stride : start + i * stride + size]
                for i in range(a["count"])
            )
        )
    return doc, arrays


def save(doc, arrays, path):
    used = sorted(
        {
            i
            for m in doc["meshes"]
            for p in m["primitives"]
            for i in [p["indices"], *p["attributes"].values()]
        }
    )
    mapping = {old: new for new, old in enumerate(used)}
    views, accessors, chunks, seen = [], [], [], {}
    size = 0
    for i in used:
        a = copy.deepcopy(doc["accessors"][i])
        data = arrays[i]
        key = hashlib.sha256(data).hexdigest()
        if key not in seen:
            padding = bytes(-size % 4)
            chunks.append(padding)
            size += len(padding)
            seen[key] = len(views)
            views.append({"buffer": 0, "byteOffset": size, "byteLength": len(data)})
            chunks.append(data)
            size += len(data)
        a["bufferView"] = seen[key]
        a.pop("byteOffset", None)
        accessors.append(a)
    for m in doc["meshes"]:
        for p in m["primitives"]:
            p["indices"] = mapping[p["indices"]]
            p["attributes"] = {k: mapping[v] for k, v in p["attributes"].items()}
    doc["accessors"], doc["bufferViews"], doc["buffers"] = (
        accessors,
        views,
        [{"byteLength": size}],
    )
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    raw += b" " * (-len(raw) % 4)
    binary = b"".join(chunks)
    binary += bytes(-len(binary) % 4)
    path.write_bytes(
        struct.pack(
            "<5I", 0x46546C67, 2, 28 + len(raw) + len(binary), len(raw), 0x4E4F534A
        )
        + raw
        + struct.pack("<2I", len(binary), 0x004E4942)
        + binary
    )


def center(points):
    return [(min(p[k] for p in points) + max(p[k] for p in points)) / 2 for k in (0, 2)]


def prepare(output):
    output = output.resolve()
    assert output.is_relative_to(ROOT / "build") and not output.exists()
    output.mkdir(parents=True)
    original, arrays = load(MODEL)
    doc = copy.deepcopy(original)
    before_arrays = arrays[:]

    def primitive(index):
        return doc["meshes"][doc["nodes"][index]["mesh"]]["primitives"][0]

    def points(index):
        return list(
            struct.iter_unpack(
                "<3f", arrays[primitive(index)["attributes"]["POSITION"]]
            )
        )

    shifts = {}
    for pot, stems, members, rise, band in [
        (6, 7, [7, 8, 9], 0.04, 0.002),
        (16, 13, [13, 14, 15], 0.0, 0.004),
    ]:
        if (
            pot == 6
            and min(p[1] for p in points(8)) > max(p[1] for p in points(pot)) + 0.005
        ):
            rise = 0.0
        ps = points(stems)
        low = min(p[1] for p in ps)
        base = center([p for p in ps if p[1] < low + band])
        target = center(points(pot))
        offset = [target[0] - base[0], rise, target[1] - base[1]]
        if max(abs(v) for v in offset) < 1e-6:
            continue
        for node in members:
            index = primitive(node)["attributes"]["POSITION"]
            transformed = [
                tuple(v[k] + offset[k] for k in range(3)) for v in points(node)
            ]
            arrays[index] = b"".join(struct.pack("<3f", *v) for v in transformed)
            doc["accessors"][index]["min"] = [
                min(v[k] for v in transformed) for k in range(3)
            ]
            doc["accessors"][index]["max"] = [
                max(v[k] for v in transformed) for k in range(3)
            ]
            shifts[index] = offset
    # A closed solid has authored inner walls. Double-sided shading reverses its
    # visible normals in the mirrored source preview; ordinary back culling keeps
    # both the real outer and inner faces without changing the assembly material.
    material = primitive(23)["material"]
    assert (
        doc["materials"][material]["name"] == "Floor plant | satin warm ivory ceramic"
    )
    doc["materials"][material]["doubleSided"] = False
    for i, (old, new) in enumerate(zip(before_arrays, arrays)):
        if i not in shifts:
            assert old == new
        else:
            for a, b in zip(
                struct.iter_unpack("<3f", old), struct.iter_unpack("<3f", new)
            ):
                assert max(abs(b[k] - a[k] - shifts[i][k]) for k in range(3)) < 3e-7
    counts_before = {
        k: len(doc[k]) for k in ("images", "textures", "materials", "meshes")
    }
    doc = share_resources(doc)
    save(doc, arrays, output / "main-planters.glb")
    # Re-read every primitive after packing: all corner attributes, including
    # normals, UVs, tangents and colors, retain their exact decoded bytes.
    packed, result = load(output / "main-planters.glb")
    for old_node, new_node in zip(original["nodes"], packed["nodes"]):
        assert old_node == new_node or {
            k: v for k, v in old_node.items() if k != "mesh"
        } == {k: v for k, v in new_node.items() if k != "mesh"}
        if "mesh" not in old_node:
            continue
        for old, new in zip(
            original["meshes"][old_node["mesh"]]["primitives"],
            packed["meshes"][new_node["mesh"]]["primitives"],
        ):
            assert before_arrays[old["indices"]] == result[new["indices"]]
            for semantic, index in old["attributes"].items():
                assert arrays[index] == result[new["attributes"][semantic]]
    textures = []
    for uri in sorted({im["uri"] for im in original["images"]}):
        source = (MODEL.parent / uri).resolve()
        raw = source.read_bytes()
        image = Image.open(io.BytesIO(raw))
        image.load()
        assert set(image.info) <= {"srgb"}, image.info
        info = PngImagePlugin.PngInfo()
        if "srgb" in image.info:
            info.add(b"sRGB", bytes([image.info["srgb"]]))
        rgba = image.convert("RGBA")
        candidates = [raw]
        images = [image]
        if image.mode == "RGBA" and image.getextrema()[3] == (255, 255):
            images.append(image.convert("RGB"))
        colors = rgba.getcolors(256)
        if colors and rgba.getextrema()[3] == (255, 255):
            palette = sorted(c for _, c in colors)
            lookup = {c: i for i, c in enumerate(palette)}
            pal = Image.new("P", image.size)
            pal.putpalette(
                [v for c in palette for v in c[:3]] + [0] * (768 - 3 * len(palette))
            )
            pal.putdata([lookup[c] for c in rgba.getdata()])
            images.append(pal)
        for candidate in images:
            buf = io.BytesIO()
            candidate.save(buf, format="PNG", optimize=True, pnginfo=info)
            candidates.append(buf.getvalue())
        encoded = min(candidates, key=len)
        check = Image.open(io.BytesIO(encoded))
        check.load()
        assert (
            check.size == image.size
            and check.convert("RGBA").tobytes() == rgba.tobytes()
        )
        assert check.info.get("srgb") == image.info.get("srgb")
        (output / source.name).write_bytes(encoded)
        textures.append(
            {
                "source": str(source.relative_to(ROOT)),
                "before": len(raw),
                "after": len(encoded),
                "sha256_before": hashlib.sha256(raw).hexdigest(),
                "sha256_after": hashlib.sha256(encoded).hexdigest(),
                "rgba_pixels_exact": True,
            }
        )
    report = {
        "source_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(
            (output / "main-planters.glb").read_bytes()
        ).hexdigest(),
        "glb_before": MODEL.stat().st_size,
        "glb_after": (output / "main-planters.glb").stat().st_size,
        "translations_by_accessor": shifts,
        "resources_before": counts_before,
        "resources_after": {k: len(doc[k]) for k in counts_before},
        "all_other_attributes_and_indices_exact": True,
        "textures": textures,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "textures"}, indent=2))
    print(
        "Texture bytes:",
        sum(t["before"] for t in textures),
        "->",
        sum(t["after"] for t in textures),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    prepare(parser.parse_args().output)
