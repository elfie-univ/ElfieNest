"""Inspect current shared prototypes with their authored source identities."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from test.godot.asset_geometry import _Model
from test.godot.asset_geometry import read_glb as _read_glb

NEST = Path(__file__).resolve().parents[2] / "godot_project/nest"

# Approved optimized prototypes recorded by 5a215035.
APPROVED_SOURCE_HASHES = {
    "furniture/shared/bedroom/bed-shared.glb": "74718497fb28c0fc385afdec6616ed6e66a35ceca8ee2e5f671a71b049516526",
    "furniture/shared/bedroom/chair.glb": "a6c308e5235c42b65a976dffcae40205abb0c6d767ad3904449f5cd6fb9898ac",
    "buildings/pod/pod-building.glb": "c12ea90b4f8f88a64e8ff5b66de2e9e7f9bab567a9985ff078eebeae2f1901e8",
}


def assert_approved_source(relative):
    path = NEST / relative
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == APPROVED_SOURCE_HASHES[relative]
    )
    return path


@lru_cache
def _bindings():
    return json.loads((NEST / "assembly/runtime-bindings.json").read_text())[
        "placements"
    ]


def _named(document):
    for node in document.get("nodes", []):
        source = node.get("extras", {})
        if source.get("review_visible", True) is False:
            continue
        if "source_name" in source:
            node["name"] = source["source_name"]
        node["extras"] = {**source, **_bindings().get(source.get("v044_path", ""), {})}
    return document


def read_glb(path):
    document, binary = _read_glb(path)
    return _named(document), binary


class NamedModel(_Model):
    def __init__(self, path):
        super().__init__(path)
        _named(self.doc)


@lru_cache
def model(path):
    return NamedModel(str(path))
