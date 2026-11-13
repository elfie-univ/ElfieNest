"""Bind the approved menu to explicit paths in the frozen, evaluated V044 scene."""

import collections
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/godot-asset-migration"


def leaves(items, path=()):
    for item in items:
        current = path + (item["label"],)
        if "children" in item:
            yield from leaves(item["children"], current)
        else:
            yield item, current


def inside(point, ring):
    x, z = point
    result = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (
            b[1] - a[1]
        ) + a[0]:
            result = not result
    return result


def main():
    catalog = json.loads(
        (
            ROOT / "godot_project/tools/nest_authoring/v044-asset-catalog.json"
        ).read_text()
    )
    entries = json.loads((BUILD / "full-inventory/static-nodes.json").read_text())
    by_path = {entry["path"]: entry for entry in entries}
    assert len(by_path) == len(entries) == 14761
    with (ROOT / catalog["source_glb"]).open("rb") as stream:
        stream.read(12)
        size, _ = struct.unpack("<II", stream.read(8))
        source = json.loads(stream.read(size))
    regions = {
        region["id"]: region
        for region in source["extras"]["landscapeRegions"]["regions"]
    }

    zone_cache = {}

    def zone(entry):
        p = entry.get(
            "instance_center", entry.get("center", entry.get("position", [0, 0, 0]))
        )
        point = [p[0], p[2]]
        key = tuple(point)
        if key in zone_cache:
            return zone_cache[key]
        for region, area in [
            ("woodland", "forest"),
            ("water", "waterside"),
            ("lakeside_paving", "waterside"),
            ("fountain", "waterside"),
            ("lawn", "meadow"),
            ("plaza", "meadow"),
        ]:
            rings = regions[region]["rings_xz_m"]
            if any(
                not ring["hole"] and inside(point, ring["points"]) for ring in rings
            ) and not any(
                ring["hole"] and inside(point, ring["points"]) for ring in rings
            ):
                zone_cache[key] = area
                return area
        # Planting beds and road holes sit between the three authored areas.
        # Assign whole source objects/batches to the nearest authored boundary;
        # never cut a mesh or rewrite instance transforms to enforce a menu zone.
        distances = {}
        for region, area in [
            ("woodland", "forest"),
            ("lawn", "meadow"),
            ("water", "waterside"),
        ]:
            best = float("inf")
            for ring in regions[region]["rings_xz_m"]:
                points = ring["points"]
                for a, b in zip(points, points[1:] + points[:1]):
                    dx, dz = b[0] - a[0], b[1] - a[1]
                    fraction = (
                        max(
                            0,
                            min(
                                1,
                                ((point[0] - a[0]) * dx + (point[1] - a[1]) * dz)
                                / (dx * dx + dz * dz),
                            ),
                        )
                        if dx * dx + dz * dz
                        else 0
                    )
                    best = min(
                        best,
                        (point[0] - a[0] - fraction * dx) ** 2
                        + (point[1] - a[1] - fraction * dz) ** 2,
                    )
            distances[area] = best
        result = min(distances, key=distances.get)
        zone_cache[key] = result
        return result

    primitives = [
        entry
        for entry in entries
        if entry["type"]
        in {
            "MeshInstance3D",
            "MultiMeshInstance3D",
            "SpotLight3D",
            "OmniLight3D",
            "DirectionalLight3D",
            "WorldEnvironment",
            "Camera3D",
            "CollisionShape3D",
            "CPUParticles3D",
            "Timer",
        }
    ]

    def layer(entry):
        return entry["extras"].get("exportLayer", "")

    def name(entry):
        return entry["path"].split("/")[-1]

    def courtyard(entry):
        return (
            not layer(entry)
            and not entry["path"].startswith("Generated/EstatePhysics")
            and entry["path"] != "Camera3D"
        )

    sets = {}
    methods = {}

    def bind(id, predicate, method):
        sets[id] = {entry["path"] for entry in primitives if predicate(entry)}
        methods[id] = method

    for category in catalog["categories"]:
        for item, _path in leaves(category["children"], (category["label"],)):
            recipe = item.get("source")
            if not recipe:
                continue

            def predicate(entry, recipe=recipe):
                e = entry["extras"]
                return all(
                    e.get("assembly") in value
                    if key == "assemblies"
                    else e.get(key) == value
                    for key, value in recipe.items()
                )

            bind(
                item["id"],
                predicate,
                "exact frozen node metadata: " + json.dumps(recipe, ensure_ascii=False),
            )

    template_layers = collections.defaultdict(set)
    for entry in primitives:
        e = entry["extras"]
        if e.get("designTemplate"):
            template_layers[e["designTemplate"]].add(
                (
                    layer(entry),
                    e.get("module"),
                    e.get("resident"),
                    e.get("designTemplateInstance"),
                    e.get("central_furnishing"),
                )
            )
    families = {
        "chairs": ["chair", "pouf", "floor_cushion", "ottoman", "stool"],
        "tables": ["table"],
        "plants": ["plant", "foliage", "fern"],
        "frames": ["frame"],
        "rugs": ["rug", "floor_cushion"],
        "lamps": ["lamp"],
        "speakers": ["speaker"],
    }
    for kind, words in families.items():
        bind(
            "common-" + kind,
            lambda e, words=words: (
                bool(e["extras"].get("designTemplate"))
                and len(template_layers[e["extras"]["designTemplate"]]) > 1
                and any(word in e["extras"]["designTemplate"] for word in words)
                and e["extras"].get("assembly")
                not in ["bed", "bedding", "pillows", "chair"]
            ),
            "source template families with multiple recorded placements; all actual variants retained",
        )

    rules = {
        "living": ("1", ["living_"]),
        "games-central": ("2", ["games_central_"]),
        "games-chess": ("2", ["games_left_chess_", "games_left_rug_"]),
        "games-console": ("2", ["games_right_console"]),
        "games-toys": ("2", ["games_front_"]),
        "games-display": (
            "2",
            [
                "games_left_curved_bookshelf",
                "games_rear_",
                "games_stair_",
                "games_niche_",
            ],
        ),
        "quiet-central": ("3", ["quiet_central_"]),
        "quiet-sofa": ("3", ["quiet_left_"]),
        "quiet-daybed": ("3", ["quiet_front_"]),
        "quiet-rear": ("3", ["quiet_rear_"]),
        "quiet-desk": ("3", ["quiet_right_"]),
    }
    for id, (floor, prefixes) in rules.items():
        bind(
            "central-" + id,
            lambda e, floor=floor, prefixes=prefixes: (
                layer(e) == "layout:central:" + floor
                and any(
                    str(
                        e["extras"].get(
                            "central_furnishing", e["extras"].get("assembly", "")
                        )
                    ).startswith(prefix)
                    for prefix in prefixes
                )
            ),
            "original central_furnishing functional group prefixes",
        )
    for i in range(1, 9):
        bind(
            f"terrace-furniture-{i:02d}",
            lambda e, i=i: layer(e) == f"layout:terrace:M{i:02d}",
            "original terrace exportLayer; shared resources remain shared",
        )
    for resident in "ABCD":
        bind(
            "bedroom-set-" + resident.lower(),
            lambda e, resident=resident: (
                layer(e) == "layout:pod"
                and e["extras"].get("module") == "M01"
                and e["extras"].get("resident") == resident
            ),
            "M01 resident slot with original transforms",
        )
    bind(
        "bedroom-layout",
        lambda e: layer(e) == "layout:pod" and e["extras"].get("module") == "M01",
        "M01 complete layout",
    )
    bind(
        "building-layout",
        lambda e: layer(e).startswith("building:") or entry_physics(e),
        "all original building placements and physics support",
    )

    bind(
        "forest-ground",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and "woodland" in name(e).lower()
        ),
        "original woodland surfaces, whole meshes",
    )
    bind(
        "forest-path",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and any(word in name(e).lower() for word in ["forest", "trail", "woodland"])
            and any(word in name(e).lower() for word in ["path", "road", "trail"])
        ),
        "original forest path surfaces, whole meshes",
    )
    bind(
        "meadow-ground",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and any(
                word in name(e).lower() for word in ["lawn", "meadow", "garden island"]
            )
        ),
        "original continuous lawn surfaces",
    )
    bind(
        "meadow-plaza",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and any(
                word in name(e).lower() for word in ["plaza", "entrance", "seven-petal"]
            )
        ),
        "original plaza surfaces",
    )
    bind(
        "shore",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and any(
                word in name(e).lower()
                for word in ["shore", "bank", "rock", "lake bed"]
            )
        ),
        "original shore and rock meshes including evaluated repairs",
    )
    bind(
        "waterside-path",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and any(
                word in name(e).lower()
                for word in ["waterfront", "lakeside", "footbridge"]
            )
            and not any(word in name(e).lower() for word in ["bench", "back frame"])
        ),
        "original waterfront surfaces",
    )
    bind(
        "picnic",
        lambda e: courtyard(e) and name(e).lower().startswith("picnic"),
        "original picnic assembly",
    )
    bind(
        "bench",
        lambda e: (
            courtyard(e)
            and name(e).lower().startswith("lakeside")
            and any(word in name(e).lower() for word in ["bench", "back frame"])
        ),
        "evaluated lakeside bench assembly",
    )
    bind(
        "tree-one",
        lambda e: (
            name(e).startswith("MERGED_STABLE_APPROVED")
            or e["extras"].get("full_source_index") == 8591
        ),
        "original primary approved tree assembly, including unnamed canopy mesh identified by frozen full_source_index 8591",
    )
    bind(
        "tree-two",
        lambda e: name(e).startswith("SECONDARY_SHARED"),
        "original secondary approved tree assembly",
    )
    bind(
        "waterfall",
        lambda e: (
            courtyard(e)
            and ("waterfall" in e["path"].lower() or "falling water" in name(e).lower())
        ),
        "evaluated waterfall geometry/effects",
    )
    bind(
        "fountain",
        lambda e: (
            courtyard(e)
            and any(
                word in e["path"].lower()
                for word in ["fountain", "spillway", "channel", "aerated jet"]
            )
        ),
        "evaluated fountain/channel geometry/effects",
    )
    bind(
        "lake",
        lambda e: (
            courtyard(e)
            and any(
                word in name(e).lower()
                for word in [
                    "lake water",
                    "lake surface",
                    "wholelake",
                    "lily",
                    "shallow bed",
                ]
            )
        ),
        "evaluated lake surfaces",
    )
    bind(
        "shared-ground",
        lambda e: (
            courtyard(e)
            and e["type"] == "MeshInstance3D"
            and any(
                word in name(e).lower()
                for word in [
                    "ground",
                    "road",
                    "lawn",
                    "plaza",
                    "bank",
                    "shore",
                    "groundpatch",
                    "boundary base",
                    "woodland",
                ]
            )
        ),
        "whole continuous and repaired ground meshes; no mesh cutting",
    )
    bind(
        "outdoor-lights",
        lambda e: (
            courtyard(e)
            and (
                "/OutdoorLighting/Fixture_" in e["path"]
                or "light" in e["path"].lower()
                and e["type"] in ["SpotLight3D", "OmniLight3D"]
                or any(word in name(e) for word in ["Rim", "Outline"])
            )
        ),
        "original outdoor fixtures and evaluated light nodes",
    )
    bind(
        "environment",
        lambda e: (
            e["type"] in ["WorldEnvironment", "DirectionalLight3D"]
            or e["extras"].get("elfienestSkySurface")
            or name(e).startswith("Transparent large arch rise")
        ),
        "frozen daytime environment, sky surfaces and sun/hemisphere lights",
    )
    for area, id in [
        ("forest", "forest-planting"),
        ("meadow", "meadow-planting"),
        ("waterside", "shore-planting"),
    ]:
        bind(
            id,
            lambda e, area=area: (
                e["type"] == "MultiMeshInstance3D"
                and e.get("source_group")
                and zone(e) == area
            ),
            "native spatial batches selected by centroid against authored region contours; batches retained whole",
        )
    all_batches = [
        e
        for e in primitives
        if e["type"] == "MultiMeshInstance3D" and e.get("source_group")
    ]
    forest_groups = {e["source_group"] for e in all_batches if zone(e) == "forest"}
    other_groups = {
        e["source_group"] for e in all_batches if zone(e) in ["meadow", "waterside"]
    }
    bind(
        "forest-library",
        lambda e: name(e) in forest_groups,
        "existing prototype groups used by forest batches",
    )
    bind(
        "plant-library",
        lambda e: name(e) in other_groups,
        "existing prototype groups used by meadow/waterside batches; original identifiers retained",
    )
    for area in ["forest", "meadow", "waterside"]:
        bind(
            area + "-layout",
            lambda e, area=area: courtyard(e) and zone(e) == area,
            "authored contours select whole source objects/native batches; continuous objects retained whole",
        )
    bind(
        "courtyard-layout",
        courtyard,
        "complete static courtyard, including cross-region content and all native batches",
    )

    plans = []
    missing = []
    for category in catalog["categories"]:
        for item, path in leaves(category["children"], (category["label"],)):
            ids = set(sets.get(item["id"], set()))
            # Preserve attached light, shape and other child nodes as a unit.
            attached = set()
            for entry in entries:
                parent = entry["path"]
                while "/" in parent:
                    parent = parent.rsplit("/", 1)[0]
                    if parent in ids:
                        attached.add(entry["path"])
                        break
            ids |= attached
            if not ids:
                missing.append(item["id"])
            plans.append(
                {
                    "id": item["id"],
                    "category": category["id"],
                    "menu": list(path),
                    "paths": sorted(ids),
                    "binding": methods.get(item["id"], "MISSING"),
                    "native_batch_boundaries_preserved": True,
                }
            )
    output = BUILD / "static-export-bindings.json"
    report = {
        "catalog_sha256": hashlib.sha256(
            (
                ROOT / "godot_project/tools/nest_authoring/v044-asset-catalog.json"
            ).read_bytes()
        ).hexdigest(),
        "snapshot_sha256": catalog["snapshot_sha256"],
        "items": plans,
        "unbound_items": missing,
        "scope": "Frozen static source assets and source-scoped views; no dynamic behavior or GLB roundtrip equivalence claim.",
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "items": len(plans),
                "unbound": missing,
                "counts": {p["id"]: len(p["paths"]) for p in plans},
            },
            ensure_ascii=False,
        )
    )


def entry_physics(entry):
    return entry["path"].startswith("Generated/EstatePhysics")


if __name__ == "__main__":
    main()
