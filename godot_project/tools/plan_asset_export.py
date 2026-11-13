"""Compile the approved menu's source candidates; never mutate/export models."""

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def leaves(items, path=()):
    for item in items:
        current = path + (item["label"],)
        if "children" in item:
            yield from leaves(item["children"], current)
        else:
            yield item, current


def main():
    catalog = json.loads(
        (
            ROOT / "godot_project/tools/nest_authoring/v044-asset-catalog.json"
        ).read_text()
    )
    source = ROOT / catalog["source_glb"]
    if digest(source) != catalog["source_sha256"]:
        raise ValueError("V044 source fingerprint changed; re-audit before planning")
    snapshot = ROOT / catalog["snapshot"]
    if digest(snapshot) != catalog["snapshot_sha256"]:
        raise ValueError("V044 evaluated snapshot fingerprint changed")
    sidecar = ROOT / catalog["instance_sidecar"]
    if digest(sidecar) != catalog["instance_sidecar_sha256"]:
        raise ValueError("V044 instance sidecar fingerprint changed")
    with sidecar.open("rb") as stream:
        magic, version, group_count, instance_count = struct.unpack(
            "<8sIII", stream.read(20)
        )
        if magic != b"ENINST01" or version != 2:
            raise ValueError("Invalid instance sidecar")
        observed = 0
        for _ in range(group_count):
            length, count = struct.unpack("<II", stream.read(8))
            if not 0 < length <= 256:
                raise ValueError("Invalid instance group name")
            stream.read(length).decode("utf8")
            stream.seek(count * 48, 1)
            observed += count
        if observed != instance_count or stream.tell() != sidecar.stat().st_size:
            raise ValueError("Instance sidecar coverage mismatch")
    with source.open("rb") as stream:
        magic, version, total = struct.unpack("<4sII", stream.read(12))
        length, kind = struct.unpack("<II", stream.read(8))
        if (magic, version, kind) != (
            b"glTF",
            2,
            0x4E4F534A,
        ) or total != source.stat().st_size:
            raise ValueError("Invalid GLB")
        model = json.loads(stream.read(length))
    regions = {
        item["id"]: item
        for item in model.get("extras", {})
        .get("landscapeRegions", {})
        .get("regions", [])
    }
    plans = []
    for category in catalog["categories"]:
        for item, path in leaves(category["children"], (category["label"],)):
            recipe = item.get("source")
            matches = []
            if recipe:
                for index, node in enumerate(model["nodes"]):
                    if "mesh" not in node:
                        continue
                    extras = node.get("extras", {})
                    if all(
                        extras.get(key) in value
                        if key == "assembly"
                        else extras.get(key) == value
                        for key, value in {
                            ("assembly" if k == "assemblies" else k): v
                            for k, v in recipe.items()
                        }.items()
                    ):
                        matches.append(index)
            region = item.get("region")
            if region and region not in regions:
                raise ValueError("Unknown authored region: " + region)
            plans.append(
                {
                    "id": item["id"],
                    "menu": list(path),
                    "source_node_candidates": matches,
                    "region_contours_available": bool(region),
                    "export_ready": False,
                    "remaining": "Compile exclusive ownership, shared references, transforms and dynamic bindings; candidates are not export instructions.",
                }
            )
    report = {
        "baseline": catalog["baseline"],
        "source_sha256": catalog["source_sha256"],
        "snapshot_sha256": catalog["snapshot_sha256"],
        "instance_sidecar_sha256": catalog["instance_sidecar_sha256"],
        "source_instance_groups": group_count,
        "source_instances": instance_count,
        "source_mesh_nodes": sum("mesh" in node for node in model["nodes"]),
        "items": plans,
        "export_ready": False,
        "limits": "Authored region source_nodes are not assumed to be integrated GLB indices. No models were exported.",
    }
    output = ROOT / "build/godot-asset-migration/export-plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "items": len(plans),
                "with_source_candidates": sum(
                    bool(item["source_node_candidates"]) for item in plans
                ),
                "region_candidates": sum(
                    item["region_contours_available"] for item in plans
                ),
                "output": str(output),
                "export_ready": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
