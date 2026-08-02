#!/usr/bin/env python3
"""Export the Linux x64 Dedicated Godot Runtime without display artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    from scripts.build_godot_web import (
        _find_godot as package_find_godot,
    )
    from scripts.build_godot_web import (
        _godot_version as package_godot_version,
    )
    from scripts.build_godot_web import (
        _project_version as package_project_version,
    )
except ModuleNotFoundError:
    from build_godot_web import (
        _find_godot as script_find_godot,
    )
    from build_godot_web import (
        _godot_version as script_godot_version,
    )
    from build_godot_web import (
        _project_version as script_project_version,
    )

    find_godot_helper = script_find_godot
    godot_version_helper = script_godot_version
    project_version_helper = script_project_version
else:
    find_godot_helper = package_find_godot
    godot_version_helper = package_godot_version
    project_version_helper = package_project_version

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = PROJECT_ROOT / "godot_project"
OUTPUT_RELATIVE_PATH = "build/components/godot-linux-dedicated"
DEFAULT_OUTPUT = PROJECT_ROOT / OUTPUT_RELATIVE_PATH
PRESET_NAME = "Linux Dedicated"
ENTRY_NAME = "ElfieNestRuntime"
FindGodot = Callable[[Optional[Path]], Optional[Path]]
GodotVersion = Callable[[Path], Optional[str]]
ProjectVersion = Callable[[], Optional[str]]

_find_godot: FindGodot = find_godot_helper
_godot_version: GodotVersion = godot_version_helper
_project_version: ProjectVersion = project_version_helper


def parse_args() -> argparse.Namespace:
    """Parse the constrained Dedicated Runtime build interface."""
    parser = argparse.ArgumentParser(
        description="Build the ElfieNest Linux Dedicated Runtime"
    )
    parser.add_argument("--godot", type=Path, help="Godot 4 executable")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="only check a bundle")
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="allow a Godot version different from project.godot",
    )
    return parser.parse_args()


def main() -> int:
    """Export exactly one Linux x64 Dedicated Runtime bundle."""
    args = parse_args()
    output = args.output.expanduser().resolve()
    if args.check:
        return _print_bundle_check(output)
    binary = _find_godot(args.godot)
    if binary is None:
        print(
            "❌ Godot 4 was not found. Specify the build tool with --godot or GODOT_BIN."
        )
        return 2
    required_version = _project_version()
    actual_version = _godot_version(binary)
    if (
        required_version
        and actual_version
        and required_version != actual_version
        and not args.allow_version_mismatch
    ):
        print(
            f"❌ Project requires Godot {required_version}; current build tool is {actual_version}."
        )
        return 2
    return _export_runtime(output, binary, actual_version or "unknown")


def _export_runtime(output: Path, binary: Path, godot_version: str) -> int:
    """Export into staging and atomically replace only a complete bundle."""
    staging = output.parent / ".godot-linux-dedicated.staging"
    previous = output.parent / ".godot-linux-dedicated.previous"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    entry = staging / ENTRY_NAME
    command = [
        str(binary),
        "--headless",
        "--path",
        str(GODOT_PROJECT),
        "--export-release",
        PRESET_NAME,
        str(entry),
    ]
    print(f"🔨 Building Linux Dedicated Runtime with Godot {godot_version}...")
    result = subprocess.run(command, cwd=GODOT_PROJECT, check=False)
    if result.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        print(
            "❌ Linux Dedicated export failed. Confirm that Linux x64 Export Templates are installed."
        )
        return result.returncode or 1
    missing = _missing_artifacts(staging)
    if missing:
        shutil.rmtree(staging, ignore_errors=True)
        print(
            "❌ Dedicated export command completed, but artifacts are incomplete: "
            + ", ".join(missing)
        )
        return 1
    _write_manifest(staging, godot_version, current_source_fingerprint())
    shutil.rmtree(previous, ignore_errors=True)
    if output.exists():
        output.replace(previous)
    staging.replace(output)
    shutil.rmtree(previous, ignore_errors=True)
    print(f"✅ Linux Dedicated Runtime generated: {output / ENTRY_NAME}")
    return 0


def _missing_artifacts(directory: Path) -> List[str]:
    """Require one executable and reject client/Web payloads."""
    entry = directory / ENTRY_NAME
    if not entry.is_file() or not os.access(entry, os.X_OK):
        return [ENTRY_NAME]
    forbidden = sorted(
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".html", ".js", ".wasm", ".pck"}
    )
    return forbidden


def _print_bundle_check(output: Path) -> int:
    """Report whether the existing bundle remains internally complete."""
    missing = _missing_artifacts(output)
    manifest = output / "build-manifest.json"
    if not manifest.is_file():
        missing.append("build-manifest.json")
    if missing:
        print(f"❌ Linux Dedicated Runtime is incomplete: {', '.join(missing)}")
        return 1
    print(f"✅ Linux Dedicated Runtime is available: {output / ENTRY_NAME}")
    return 0


def current_source_fingerprint() -> str:
    """Hash Godot source but never include generated editor cache."""
    digest = hashlib.sha256()
    for path in sorted(item for item in GODOT_PROJECT.rglob("*") if item.is_file()):
        relative = path.relative_to(GODOT_PROJECT)
        if ".godot" in relative.parts or relative.suffix in {".import", ".tmp"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_is_current(output: Path) -> bool:
    """Check the Dedicated manifest, executable and source fingerprint."""
    if _missing_artifacts(output):
        return False
    manifest_path = output / "build-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(manifest, dict):
        return False
    if manifest.get("source_fingerprint") != current_source_fingerprint():
        return False
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != {ENTRY_NAME}:
        return False
    metadata = files[ENTRY_NAME]
    if not isinstance(metadata, dict):
        return False
    entry = output / ENTRY_NAME
    return (
        metadata.get("bytes") == entry.stat().st_size
        and metadata.get("sha256") == hashlib.sha256(entry.read_bytes()).hexdigest()
    )


def _write_manifest(directory: Path, godot_version: str, fingerprint: str) -> None:
    """Write a typed-by-shape artifact digest for the single executable."""
    entry = directory / ENTRY_NAME
    manifest: Dict[str, object] = {
        "schema_version": 1,
        "godot_version": godot_version,
        "preset": PRESET_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": ENTRY_NAME,
        "source_fingerprint": fingerprint,
        "files": {
            ENTRY_NAME: {
                "bytes": entry.stat().st_size,
                "sha256": hashlib.sha256(entry.read_bytes()).hexdigest(),
            }
        },
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
