"""Generate the pod upper interior finish after geometry; write a build candidate only."""

import argparse
import collections
import copy
import hashlib
import json
import math
import struct
from pathlib import Path

from devtools.asset_design.glb_resources import encode_glb, read_glb
from devtools.asset_design.object_glb import extract_glb

ROOT = Path(__file__).resolve().parents[6]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
W = args.output.resolve()
W.relative_to(ROOT / "build")
W.mkdir(parents=True, exist_ok=False)
S = Path(__file__).with_name("model.glb")
(W / "before.glb").write_bytes(S.read_bytes())
(W / "before-build.json").write_bytes(S.with_name("build.json").read_bytes())
D, B = read_glb(S)
old = copy.deepcopy(D)
binary = bytearray(B)
ivory = next(
    i
    for i, m in enumerate(D["materials"])
    if m.get("name") == "INTERIOR • warm ivory #F2EDE3"
)


def rows(i):
    a = D["accessors"][i]
    v = D["bufferViews"][a["bufferView"]]
    n = {"VEC3": 3, "VEC4": 4, "SCALAR": 1}[a["type"]]
    f = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]]
    rr = [
        struct.unpack_from(
            "<" + f * n,
            B,
            v.get("byteOffset", 0)
            + a.get("byteOffset", 0)
            + j * v.get("byteStride", struct.calcsize(f) * n),
        )
        for j in range(a["count"])
    ]
    if a.get("normalized"):
        rr = [tuple(x / 255 for x in r) for r in rr]
    return rr


shells = [
    (i, n)
    for i, n in enumerate(D["nodes"])
    if "mesh" in n
    and n.get("extras", {}).get("source_name") == "ROOM • sculpted continuous shell"
]
ni, node = next((i, n) for i, n in shells if n["extras"]["module"] == "M01")
mid = node["mesh"]
external = D["meshes"][mid]["primitives"][0]["material"]


# Original crown cross-section. Return owners are explicit and exclude
# the stair-facing cut surfaces from the room finish. Classify *after* geometry.
def field(v):
    p, n = v[:2]
    x, y, z = p
    # Original crown: outer (3.51,3.09), inner (3.10,2.68), rounded crest
    # centred at (3.305,2.885). Its medial superellipse defines the paint seam.
    f = (abs(x) / 3.305) ** 3.5 + (abs(z) / 2.885) ** 3.5 - 1.0
    # The opening-end faces belong to exterior wall returns, including the short
    # pier. These planes are evaluated continuously, never by triangle centroid.
    if 0.40 < x < 1.10 and z < -2.30:
        f = max(f, x - 0.70)
    if 2.00 < x < 2.85 and z < -1.95:
        f = max(f, 2.24 - x)
    return f


def interpolate(a, b, t):
    return tuple(
        tuple(a[k][j] + t * (b[k][j] - a[k][j]) for j in range(len(a[k])))
        for k in range(len(a))
    )


def clip(poly, fn, negative=True):
    if not poly:
        return []
    out = []
    a = poly[-1]
    fa = fn(a) * (1 if negative else -1)
    for b in poly:
        fb = fn(b) * (1 if negative else -1)
        if (fa <= 0) != (fb <= 0):
            # Exact shared scalar roots along each original edge, independent of winding.
            lo, hi = 0.0, 1.0
            for _ in range(32):
                t = (lo + hi) / 2
                fm = fn(interpolate(a, b, t)) * (1 if negative else -1)
                if (fm <= 0) == (fa <= 0):
                    lo = t
                else:
                    hi = t
            out.append(interpolate(a, b, (lo + hi) / 2))
        if fb <= 0:
            out.append(b)
        a, fa = b, fb
    return out


proof = {
    "maxSerializedVertexDeviationM": 0.0,
    "maxBarycentricUnderflow": 0.0,
    "maxTriangleAreaResidualM2": 0.0,
}
source_triangle = None
emitted_area = 0.0
patches = collections.defaultdict(list)
keeps = []
counts = collections.Counter()
protected = collections.Counter()
baseline = collections.Counter()


def emit(poly, owner, colored):
    global emitted_area
    if len(poly) < 3:
        return
    for i in range(1, len(poly) - 1):
        tri = [poly[0], poly[i], poly[i + 1]]
        a, b, c = [v[0] for v in tri]
        u = [b[j] - a[j] for j in range(3)]
        w = [c[j] - a[j] for j in range(3)]
        cross = [
            u[1] * w[2] - u[2] * w[1],
            u[2] * w[0] - u[0] * w[2],
            u[0] * w[1] - u[1] * w[0],
        ]
        area = math.sqrt(sum(v * v for v in cross)) / 2
        if area < 5e-13:
            continue
        emitted_area += area
        for vertex in tri:
            p = vertex[0]
            weights = vertex[3]
            expected = tuple(
                sum(source_triangle[k][axis] * weights[k] for k in range(3))
                for axis in range(3)
            )
            packed = struct.unpack("<3f", struct.pack("<3f", *p))
            proof["maxSerializedVertexDeviationM"] = max(
                proof["maxSerializedVertexDeviationM"], math.dist(packed, expected)
            )
            proof["maxBarycentricUnderflow"] = max(
                proof["maxBarycentricUnderflow"], -min(weights)
            )
        patches[(owner, colored)].extend(tri)


for pr in old["meshes"][mid]["primitives"]:
    ps = rows(pr["attributes"]["POSITION"])
    ns = rows(pr["attributes"]["NORMAL"])
    cc = rows(pr["attributes"]["COLOR_0"]) if "COLOR_0" in pr["attributes"] else None
    ids = [r[0] for r in rows(pr["indices"])]
    keep = []
    for j in range(0, len(ids), 3):
        ii = ids[j : j + 3]
        if max(ps[k][1] for k in ii) <= 3.1:
            keep.extend(ii)
            continue
        source_triangle = [ps[k] for k in ii]
        emitted_area = 0.0
        vs = [
            (
                ps[k],
                ns[k],
                tuple(cc[k]) if cc is not None else (1.0, 1.0, 1.0),
                tuple(1.0 if a == j else 0.0 for a in range(3)),
            )
            for j, k in enumerate(ii)
        ]
        upper = clip(vs, lambda v: 3.1 - v[0][1])
        lower = clip(vs, lambda v: v[0][1] - 3.1)
        emit(lower, "original" + str(pr["material"]), cc is not None)
        inside = clip(upper, field)
        outside = clip(upper, field, False)
        emit(inside, "ivory", False)
        emit(outside, "exterior", cc is not None)
        counts["upperSourceTriangles"] += 1
        if len(inside) >= 3 and len(outside) >= 3:
            counts["boundaryCrossingTriangles"] += 1
        a, b, c = source_triangle
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        area = (
            math.sqrt(
                (u[1] * v[2] - u[2] * v[1]) ** 2
                + (u[2] * v[0] - u[0] * v[2]) ** 2
                + (u[0] * v[1] - u[1] * v[0]) ** 2
            )
            / 2
        )
        proof["maxTriangleAreaResidualM2"] = max(
            proof["maxTriangleAreaResidualM2"], abs(area - emitted_area)
        )
    keeps.append((copy.deepcopy(pr), keep))


# Append new local arrays only. Keep existing lower-wall attributes/indices exact.
def accessor(rr, kind, ctype=5126):
    binary.extend(bytes(-len(binary) % 4))
    off = len(binary)
    flat = [v for r in rr for v in r]
    fmt = "I" if ctype == 5125 else "f"
    binary.extend(struct.pack("<" + fmt * len(flat), *flat))
    vi = len(D["bufferViews"])
    D["bufferViews"].append(
        {"buffer": 0, "byteOffset": off, "byteLength": len(binary) - off}
    )
    a = {"bufferView": vi, "componentType": ctype, "count": len(rr), "type": kind}
    if kind == "VEC3" and ctype == 5126:
        a.update(
            min=[min(r[k] for r in rr) for k in range(3)],
            max=[max(r[k] for r in rr) for k in range(3)],
        )
    ai = len(D["accessors"])
    D["accessors"].append(a)
    return ai


prims = []
for p, ii in keeps:
    if ii:
        p["indices"] = accessor([(k,) for k in ii], "SCALAR", 5125)
        prims.append(p)
for (owner, colored), vs in patches.items():
    lookup = {}
    ps = []
    ns = []
    cs = []
    ii = []
    for vertex in vs:
        p, n, c = vertex[:3]
        # Normals are interpolated, then normalized; original surface positions stay on
        # their source triangles. No added wall, offset, decimation or topology remesh.
        length = math.sqrt(sum(x * x for x in n))
        n = tuple(x / length for x in n) if length > 1e-15 else n
        key = struct.pack(
            "<" + ("9f" if colored else "6f"), *(p + n + (c if colored else ()))
        )
        if key not in lookup:
            lookup[key] = len(ps)
            ps.append(p)
            ns.append(n)
            cs.append(c)
        ii.append((lookup[key],))
    attrs = {"POSITION": accessor(ps, "VEC3"), "NORMAL": accessor(ns, "VEC3")}
    if colored:
        attrs["COLOR_0"] = accessor(cs, "VEC3")
    mat = (
        ivory
        if owner == "ivory"
        else external
        if owner == "exterior"
        else int(owner.removeprefix("original"))
    )
    prims.append(
        {"attributes": attrs, "indices": accessor(ii, "SCALAR", 5125), "material": mat}
    )
changed = []
for _i, n in shells:
    m = n["mesh"]
    ext = old["meshes"][m]["primitives"][0]["material"]
    p = copy.deepcopy(prims)
    for v in p:
        if v["material"] == external:
            v["material"] = ext
    D["meshes"][m]["primitives"] = p
    changed.append(m)
D["buffers"][0]["byteLength"] = len(binary)
assert D["nodes"] == old["nodes"] and D["materials"] == old["materials"]
assert all(m == D["meshes"][i] for i, m in enumerate(old["meshes"]) if i not in changed)
raw = encode_glb(D, bytes(binary))
(W / "candidate.glb").write_bytes(raw)
selected = [
    i for i, n in enumerate(D["nodes"]) if n.get("extras", {}).get("module") == "M01"
]
review, _ = extract_glb(W / "candidate.glb", selected)
(W / "after-review.glb").write_bytes(review)
assert (
    proof["maxSerializedVertexDeviationM"] < 0.000001
    and proof["maxBarycentricUnderflow"] < 1e-10
    and proof["maxTriangleAreaResidualM2"] < 1e-9
), proof
r = dict(counts)
r.update(proof)
r.update(
    beforeSHA256=hashlib.sha256(S.read_bytes()).hexdigest(),
    candidateSHA256=hashlib.sha256(raw).hexdigest(),
    changedMeshes=changed,
    noDecimation=True,
    nodesAndMaterialDefinitionsUnchanged=True,
    otherMeshesUnchanged=True,
    method="reset upper finish ownership; original crown medial cross-section with explicit exterior opening returns; split boundary-crossing triangles on the existing surface",
)
(W / "result.json").write_text(json.dumps(r, indent=2))
print(json.dumps(r), flush=True)
