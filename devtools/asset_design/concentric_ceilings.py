"""Align central ceiling fixtures and reuse their authored second ring geometry."""

import argparse
import copy
from pathlib import Path

from devtools.asset_design.glb_resources import encode_glb, read_glb


def align_ceilings(document: dict) -> dict:
    result = copy.deepcopy(document)
    nodes = result["nodes"]
    by_name = {node.get("name", ""): node for node in nodes}
    centres = {1: (-0.28, 0.65), 2: (0.0, 0.85), 3: (0.0, 1.35)}
    ceiling_heights = {1: 4.06, 2: 6.86, 3: 9.66}

    def translate(node: dict, offset: tuple[float, float, float]) -> None:
        if "matrix" in node:
            for axis in range(3):
                node["matrix"][12 + axis] += offset[axis]
        else:
            old = node.get("translation", [0.0, 0.0, 0.0])
            node["translation"] = [old[i] + offset[i] for i in range(3)]

    # Move the whole authored L3 fixture, including its rim and four downlights.
    # Ring geometry and all source material/texture/binary buffers stay intact.
    disc = by_name["Working L3 circular opal ceiling diffuser"]
    position = disc.get("translation", disc.get("matrix", [0.0] * 16)[12:15])
    offset = (centres[3][0] - position[0], 0.0, centres[3][1] - position[2])
    for node in nodes:
        if (
            node.get("name", "").startswith("Working L3 ")
            and node.get("extras", {}).get("lighting_kind") == "ceiling"
        ):
            translate(node, offset)

    parents = {
        child: index
        for index, node in enumerate(nodes)
        for child in node.get("children", [])
    }
    for finish in ["ivory recess", "continuous warm diffuser"]:
        original_name = "L3 ceiling ring 2 " + finish
        original = by_name[original_name]
        original_index = next(i for i, node in enumerate(nodes) if node is original)
        for floor in [1, 2]:
            name = f"L{floor} ceiling ring 2 {finish}"
            if name in by_name:
                raise ValueError(f"Second ring already exists: {name}")
            node = copy.deepcopy(original)
            node["name"] = name
            node["extras"]["floor"] = floor
            node["extras"].pop("source_name", None)
            node["extras"]["concentric_ceiling_revision"] = 1
            translate(
                node,
                (
                    centres[floor][0],
                    ceiling_heights[floor] - ceiling_heights[3],
                    centres[floor][1] - centres[3][1],
                ),
            )
            index = len(nodes)
            nodes.append(node)
            if original_index in parents:
                nodes[parents[original_index]]["children"].append(index)
            else:
                for scene in result["scenes"]:
                    if original_index in scene.get("nodes", []):
                        scene["nodes"].append(index)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    document, binary = read_glb(args.source)
    result = align_ceilings(document)
    args.output.write_bytes(encode_glb(result, binary))


if __name__ == "__main__":
    main()
