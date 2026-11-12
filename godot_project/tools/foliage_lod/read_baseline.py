# Read-only SCN decoder, based on Godot 4.7 binary resource / PackedScene formats.
# Exports a build-only baseline; never invokes Godot or modifies its cache.
import collections
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[3])


class Reader:
    def __init__(self, b):
        self.b = b
        self.p = 0
        self.strings = []

    def val(self, fmt):
        v = struct.unpack_from("<" + fmt, self.b, self.p)
        self.p += struct.calcsize("<" + fmt)
        return v[0] if len(v) == 1 else v

    def u(self):
        return self.val("I")

    def s(self):
        n = self.u()
        v = self.b[self.p : self.p + n]
        self.p += n
        return v.rstrip(b"\0").decode()

    def v(self):
        t = self.u()
        if t in [1, 42, 43]:
            return None
        if t == 2:
            return bool(self.u())
        if t == 3:
            return self.val("i")
        if t == 4:
            return self.val("f")
        if t == 40:
            return self.val("q")
        if t == 41:
            return self.val("d")
        if t in [5, 44]:
            return self.s()
        if t in [10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 50, 52]:
            n = {
                10: 2,
                11: 4,
                12: 3,
                13: 4,
                14: 4,
                15: 6,
                16: 9,
                17: 12,
                18: 6,
                20: 4,
                50: 4,
                52: 16,
            }[t]
            return ("T" + str(t), self.val("f" * n))
        if t == 24:
            k = self.u()
            if k == 0:
                return None
            if k == 2:
                return ("internal", self.u())
            if k == 3:
                return ("external", self.u())
            raise ValueError(("object", k, self.p))
        if t == 22:
            a = self.val("H")
            b = self.val("H")
            return ("nodepath", [self.u() for _ in range(a + (b & 32767))])
        if t == 26:
            n = self.u() & 0x7FFFFFFF
            out = {}
            for _ in range(n):
                k = self.v()
                out[k] = self.v()
            return out
        if t == 30:
            return [self.v() for _ in range(self.u() & 0x7FFFFFFF)]
        if t == 34:
            return [self.s() for _ in range(self.u())]
        if t == 31:
            n = self.u()
            v = self.b[self.p : self.p + n]
            self.p += (n + 3) // 4 * 4
            return ("bytes", v.hex())
        if t in [32, 33, 35, 36, 37, 48, 49, 53]:
            n = self.u()
            kind = {
                32: "i",
                33: "f",
                35: "fff",
                36: "ffff",
                37: "ff",
                48: "q",
                49: "d",
                53: "ffff",
            }[t]
            if n == 0:
                return []
            result = self.val(kind * n)
            return [result] if n * len(kind) == 1 else list(result)
        raise ValueError(("variant", t, self.p))


def readscene(path):
    b = path.read_bytes()
    if b[:4] == b"RSCC":
        mode, size, total = struct.unpack_from("<III", b, 4)
        assert mode == 2
        count = total // size + 1
        sizes = struct.unpack_from("<" + "I" * count, b, 16)
        start = 16 + 4 * count
        data = []
        for n in sizes:
            data.append(b[start : start + n])
            start += n
        b = subprocess.run(
            [shutil.which("zstd") or "/opt/homebrew/bin/zstd", "-d", "-q", "-c"],
            input=b"".join(data),
            capture_output=True,
            check=True,
        ).stdout
        assert len(b) == total
    else:
        assert b[:4] == b"RSRC"
        b = b[4:]
    r = Reader(b)
    header = r.val("IIIII")
    assert header[0] == 0
    typ = r.s()
    r.val("Q")
    flags = r.u()
    r.val("Q")
    assert not flags & 4
    if flags & 8:
        r.s()
    r.p += 44
    r.strings = [r.s() for _ in range(r.u())]
    ext = []
    for _ in range(r.u()):
        a = r.s()
        p = r.s()
        if flags & 2:
            r.val("Q")
        ext.append((a, p))
    internal = []
    for _ in range(r.u()):
        internal.append((r.s(), r.val("Q")))
    out = {}
    for name, off in internal:
        r.p = off
        typ = r.s()
        props = {}
        for _ in range(r.u()):
            prop = r.strings[r.u()]
            props[prop] = r.v()
        out[name] = (typ, props)
    return ext, out


IDENTITY_BASIS = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def mul(a, b):
    return tuple(
        sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3))
        for r in range(3)
        for c in range(3)
    )


def scale(a):
    return max(math.sqrt(sum(a[r * 3 + c] ** 2 for r in range(3))) for c in range(3))


cache = {}


def nodes(path):
    if path in cache:
        return cache[path]
    ex, rs = readscene(path)
    q = next(p["_bundled"] for t, p in rs.values() if t == "PackedScene")
    a = q["nodes"]
    names = q["names"]
    vv = q["variants"]
    out = []
    at = 0
    for _i in range(q["node_count"]):
        parent, owner, typ, name, inst, count = a[at : at + 6]
        at += 6
        props = {}
        for _ in range(count):
            pn, pv = a[at : at + 2]
            at += 2
            props[names[pn]] = vv[pv]
        pool = props.get("shared_instance_buffers")
        if pool:
            assert pool[0] == "internal"
            props["shared_instance_buffers"] = list(rs.values())[pool[1]][1]["buffers"]
        count = a[at]
        at += count + 1
        out.append(
            {
                "parent": parent,
                "name": names[name & ((1 << 18) - 1)],
                "typ": names[typ] if 0 <= typ < len(names) else "instanced",
                "inst": vv[inst] if inst >= 0 else None,
                "props": props,
            }
        )
    assert at == len(a)
    cache[path] = (ex, out)
    return ex, out


records = []
anisotropies = []
shear = []
stretch_upper = []
root = Path("godot_project")
results = collections.defaultdict(list)
issues = []
mounts = []


def walk(rel, parent=IDENTITY_BASIS, override=None, chain=""):
    path = root / rel
    ex, ns = nodes(path)
    worlds = []
    libs = []
    for i, n in enumerate(ns):
        props = dict(n["props"])
        if i == 0 and override:
            props.update(override)
        par = n["parent"]
        if par >= len(worlds):
            raise ValueError(("path-parent", rel, par))
        up = parent if par < 0 else worlds[par]
        t = props.get("transform")
        local = t[1][:9] if t else IDENTITY_BASIS
        assert not any(
            k in props for k in ["scale", "rotation", "quaternion", "basis"]
        ), ("otherbasis", props.keys())
        if props.get("top_level", False):
            up = IDENTITY_BASIS
        w = mul(up, local)
        worlds.append(w)
        lib = props.get("library")
        lib = ex[lib[1]][1] if lib else (None if par < 0 else libs[par])
        libs.append(lib)
        inst = n["inst"]
        full = chain + "/" + n["name"]
        if inst and inst[0] == "external":
            target = ex[inst[1]][1]
            if target.endswith(".scn"):
                mounts.append((target, scale(w)))
                walk(target[6:], up, props, full)
            else:
                issues.append(("non-scn", target))
        if n["typ"] in ["MultiMeshInstance3D", "MeshInstance3D"] and lib:
            results[(lib.split("/")[-1], n["typ"])].append(
                (scale(w), rel, n["name"], props.get("lod_bias", 1.0))
            )

        if (
            n["typ"] == "MultiMeshInstance3D"
            and lib
            and lib.endswith("/forest-foliage.glb")
        ):
            parent_props = ns[par]["props"]
            siblings = [j for j, x in enumerate(ns) if x["parent"] == par]
            slot = siblings.index(i)
            source_names = parent_props["source_nodes"]
            assert len(source_names) == len(siblings)
            if source_names[slot] == "part_00006":
                data = parent_props["instance_batches"][slot]
                buf = (
                    data["buffer"]
                    if "buffer" in data
                    else parent_props["shared_instance_buffers"][data["buffer_index"]]
                )
                count = data["instance_count"]
                stride = (
                    12 + 4 * int(data["use_colors"]) + 4 * int(data["use_custom_data"])
                )
                assert data["transform_format"] == 1 and len(buf) == count * stride
                visible = data["visible_instance_count"]
                visible = count if visible < 0 else visible
                local_scales = []
                world_scales = []
                for j in range(count):
                    raw = buf[j * stride : j * stride + 12]
                    basis = tuple(raw[r * 4 + c] for r in range(3) for c in range(3))
                    global_basis = mul(w, basis)
                    local_scales.append(scale(basis))
                    world_scales.append(scale(global_basis))
                    gram = [
                        [
                            sum(
                                global_basis[r * 3 + c] * global_basis[r * 3 + k]
                                for r in range(3)
                            )
                            for k in range(3)
                        ]
                        for c in range(3)
                    ]
                    stretch_upper.append(
                        math.sqrt(max(sum(abs(x) for x in row) for row in gram))
                        * (1 + 1e-6)
                    )
                    axes = [
                        math.sqrt(sum(global_basis[r * 3 + c] ** 2 for r in range(3)))
                        for c in range(3)
                    ]
                    anisotropies.append(max(axes) / min(axes))
                    shear.append(
                        max(
                            abs(
                                sum(
                                    global_basis[r * 3 + c] * global_basis[r * 3 + k]
                                    for r in range(3)
                                )
                            )
                            / (axes[c] * axes[k])
                            for c, k in [(0, 1), (0, 2), (1, 2)]
                        )
                    )
                records.append(
                    {
                        "scene": rel,
                        "node": n["name"],
                        "source_path": props.get("metadata/v044_path"),
                        "count": count,
                        "visible": visible,
                        "node_scale": scale(w),
                        "local": local_scales,
                        "world": world_scales,
                    }
                )


walk("nest/courtyard/overview/courtyard-all/courtyard-covered.scn")


def stats(xs):
    a = sorted(xs)

    def q(p):
        at = (len(a) - 1) * p
        lo = int(at)
        hi = min(lo + 1, len(a) - 1)
        return a[lo] + (a[hi] - a[lo]) * (at - lo)

    return {"n": len(a), "min": a[0], "p50": q(0.5), "p95": q(0.95), "max": a[-1]}


DEST = Path(
    sys.argv[1] if len(sys.argv) > 1 else "build/godot_assets/foliage-lod-regenerated"
).resolve()
assert DEST.is_relative_to(Path("build").resolve())
DEST.mkdir(parents=True, exist_ok=True)
glb = Path("godot_project/nest/courtyard/parts/forest/forest-foliage.glb")
cache_rel = re.search(
    r'^path="res://([^"]+)"', Path(str(glb) + ".import").read_text(), re.M
).group(1)
cachepath = Path("godot_project") / cache_rel
_, resources = readscene(cachepath)
key, props = next(
    (k, p)
    for k, (t, p) in resources.items()
    if t == "ArrayMesh"
    and p.get("resource_name", "").endswith(
        "b2fff028fe3e85e28aca2510c9974010f8e05cd3519fd10f402546d7cd687f87"
    )
)
shadow_ref = props["shadow_mesh"]
assert shadow_ref[0] == "internal"
shadow = list(resources.values())[shadow_ref[1]][1]
# Re-generation may read a cache already containing our one extra LOD.
# Strip only the exact previous sidecar pair; every remaining field is baseline.
sidecar = glb.with_suffix(".lods.json")
if sidecar.exists():
    old = json.loads(sidecar.read_text())
    for label, surface in [
        ("main", props["_surfaces"][0]),
        ("shadow", shadow["_surfaces"][0]),
    ]:
        lods = surface.get("lods", [])
        if len(lods) == 6:
            expected = old[label]
            assert abs(lods[0] - old["lod_edge"]) < 1e-8
            assert lods[1][1] == expected["indices_hex"], (
                "Unknown existing LOD; refuse to strip"
            )
            surface["lods"] = lods[2:]
# Named resource indices address the binary file's ordered resource table.
assert shadow["_surfaces"][0]["index_count"] == 6912
report = {
    "source_path": str(glb),
    "source_sha256": hashlib.sha256(glb.read_bytes()).hexdigest(),
    "imported_cache_path": str(cachepath),
    "imported_cache_sha256": hashlib.sha256(cachepath.read_bytes()).hexdigest(),
    "mesh_name": props["resource_name"],
    "surface": props["_surfaces"][0],
    "shadow_surface": shadow["_surfaces"][0],
    "instances": sum(r["count"] for r in records),
    "source_batches": len(records),
    "instance_model_scale": stats([v for r in records for v in r["world"]]),
    "world_stretch_upper": max(stretch_upper),
    "world_stretch_method": "sqrt(max absolute row sum of B^T B), with 1e-6 upward margin; all canonical instance buffers and composed scene bases",
    "scene_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in cache},
    "input_checks": {
        "source_batches_203": len(records) == 203,
        "instances_22878": sum(r["count"] for r in records) == 22878,
    },
}
assert all(report["input_checks"].values())
(DEST / "baseline.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    "BASELINE",
    report["source_sha256"],
    "world_stretch_upper",
    report["world_stretch_upper"],
    "shadow_ref",
    shadow_ref,
)
