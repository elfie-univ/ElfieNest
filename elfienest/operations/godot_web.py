"""Godot Web Runtime 产物检查。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from elfienest.ui import STATIC_DIR

GODOT_WEB_DIR = STATIC_DIR / "godot-web"
GODOT_WEB_ENTRY = GODOT_WEB_DIR / "elfienest.html"
GODOT_WEB_MANIFEST = GODOT_WEB_DIR / "build-manifest.json"
REQUIRED_SUFFIXES = (".html", ".js", ".wasm", ".pck")


@dataclass(frozen=True)
class GodotWebBundleStatus:
    ready: bool
    entry_url: str
    directory: Path
    missing: Tuple[str, ...]
    manifest: Dict[str, object]


def inspect_godot_web_bundle(
    directory: Path = GODOT_WEB_DIR,
) -> GodotWebBundleStatus:
    files = tuple(path for path in directory.glob("elfienest.*") if path.is_file())
    suffixes = {path.suffix for path in files}
    missing = tuple(suffix for suffix in REQUIRED_SUFFIXES if suffix not in suffixes)
    manifest_path = directory / GODOT_WEB_MANIFEST.name
    manifest: Dict[str, object] = {}
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            manifest = payload
    if not manifest_path.is_file():
        missing += (GODOT_WEB_MANIFEST.name,)
    return GodotWebBundleStatus(
        ready=not missing,
        entry_url="/static/godot-web/elfienest.html",
        directory=directory,
        missing=missing,
        manifest=manifest,
    )
