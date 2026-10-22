"""Resolve registered furniture mothers for a frozen, verifiable preview plan."""

import copy
import math

from devtools.asset_design.deletion import checked_file
from devtools.asset_design.glb_resources import read_glb


def resolve_templates(root, entry, objects, state):
    """Keep host placements immutable; resolve geometry from the confirmed mother GLB."""
    doc, _ = read_glb(checked_file(root.resolve(), entry["file"]))
    instances = doc.get("extras", {}).get("templateInstances", [])
    if not isinstance(instances, list):
        raise ValueError("Invalid furniture instance list")
    resolved = []
    identities = set()
    for original in instances:
        instance = copy.deepcopy(original)
        identifier = instance["object"]
        obj = objects.get(identifier)
        if not obj or obj.get("group") not in {"part", "kit"} or not obj["versions"]:
            raise ValueError("Furniture mother unavailable: " + identifier)
        if instance["id"] in identities:
            raise ValueError("Duplicate furniture instance")
        identities.add(instance["id"])
        current = state["current"].get(identifier)
        version = next(
            (v for v in obj["versions"] if current and v["id"] == current["version"]),
            None,
        )
        if not version or version.get("contentDigest") != current.get("contentDigest"):
            raise ValueError("Furniture mother is not confirmed: " + identifier)
        mother, _ = read_glb(checked_file(root.resolve(), version["file"]))
        if mother.get("extras", {}).get("templateInstances"):
            raise ValueError("Nested furniture mothers are not supported")
        available = set(version["nodes"])
        if not instance.get("bindings"):
            raise ValueError("Empty furniture instance")
        for binding in instance["bindings"]:
            index = binding["node"]
            if type(index) is not int or index not in available:
                raise ValueError("Furniture mother node unavailable")
            node = mother["nodes"][index]
            if binding.get("nodeName", node.get("name")) != node.get("name"):
                raise ValueError("Furniture mother node identity changed")
            matrix = binding["matrix"]
            if (
                not isinstance(matrix, list)
                or len(matrix) != 16
                or not all(
                    isinstance(n, (float, int))
                    and not isinstance(n, bool)
                    and math.isfinite(n)
                    for n in matrix
                )
            ):
                raise ValueError("Invalid furniture placement")
            materials = binding.get("materials", [])
            primitives = mother["meshes"][node["mesh"]]["primitives"]
            if len(materials) != len(primitives) or any(
                m is not None
                and (type(m) is not int or not 0 <= m < len(doc.get("materials", [])))
                for m in materials
            ):
                raise ValueError("Invalid furniture material binding")
            source = binding.get("sourceNode")
            if source is not None and (
                type(source) is not int or not 0 <= source < len(doc["nodes"])
            ):
                raise ValueError("Invalid furniture source node")
        instance.update(
            {key: version[key] for key in ("file", "digest", "contentDigest")}
        )
        instance["version"] = version["id"]
        instance["nodes"] = sorted({b["node"] for b in instance["bindings"]})
        resolved.append(instance)
    return resolved


def template_dependencies(entries):
    """Deduplicate the mother identities pinned by one or more scene layers."""
    dependencies = {}
    for entry in entries:
        for instance in entry.get("templateInstances", []):
            key = instance["object"]
            value = {
                k: instance[k] for k in ("object", "version", "digest", "contentDigest")
            }
            if key in dependencies and dependencies[key] != value:
                raise ValueError("Conflicting furniture mothers")
            dependencies[key] = value
    return [dependencies[key] for key in sorted(dependencies)]
