#!/usr/bin/env python3
"""Export the Linux x64 Dedicated Godot Runtime without display artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.godot.artifacts.export_boundary import export_boundary_manifest
from infrastructure.godot.artifacts.species_package_validation import (
    SpeciesPackageValidationError,
    validate_source_species_packages,
)
from infrastructure.godot.artifacts.web_build import (
    _project_version as project_version_helper,
)
from infrastructure.godot.runner import (
    find_godot as find_godot_helper,
)
from infrastructure.godot.runner import (
    forward_output,
    run_headless,
)
from infrastructure.godot.runner import (
    godot_version as godot_version_helper,
)
from infrastructure.persistence.configuration.species import load_species_catalog
from scripts.godot_species_validation import run_godot_species_validation

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
    try:
        species_package_ids = validate_source_species_packages(
            config_root=PROJECT_ROOT / "config",
            godot_project=GODOT_PROJECT,
            godot_runner=run_godot_species_validation,
            godot_binary=binary,
            godot_version=godot_version,
        )
    except SpeciesPackageValidationError as error:
        print(f"❌ Species package validation failed: {error}")
        return 1
    staging = output.parent / ".godot-linux-dedicated.staging"
    previous = output.parent / ".godot-linux-dedicated.previous"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    entry = staging / ENTRY_NAME
    print(f"🔨 Building Linux Dedicated Runtime with Godot {godot_version}...")
    result = run_headless(
        binary,
        GODOT_PROJECT,
        ("--export-release", PRESET_NAME, str(entry)),
        timeout_seconds=600.0,
        godot_version=godot_version,
        purpose="dedicated-runtime-export",
    )
    forward_output(result)
    if result.exit_code != 0:
        shutil.rmtree(staging, ignore_errors=True)
        if result.crashed:
            print(
                "❌ Godot crashed during Dedicated Runtime export; no retry was attempted."
            )
        print(
            "❌ Linux Dedicated export failed. Confirm that Linux x64 Export Templates are installed."
        )
        return result.exit_code
    missing = _missing_artifacts(staging)
    if missing:
        shutil.rmtree(staging, ignore_errors=True)
        print(
            "❌ Dedicated export command completed, but artifacts are incomplete: "
            + ", ".join(missing)
        )
        return 1
    _write_manifest(
        staging,
        godot_version,
        current_source_fingerprint(),
        current_species_catalog_digest(),
        species_package_ids,
    )
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


def current_species_catalog_digest() -> str:
    """Return the bundled species catalog digest paired with this export."""
    return load_species_catalog(root=PROJECT_ROOT / "config").digest


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
    try:
        schema_version = int(manifest.get("schema_version", 0))
    except (TypeError, ValueError):
        return False
    if schema_version < 2:
        return False
    if manifest.get("export_boundary") != export_boundary_manifest():
        return False
    if manifest.get("source_fingerprint") != current_source_fingerprint():
        return False
    if manifest.get("species_catalog_digest") != current_species_catalog_digest():
        return False
    expected_species = tuple(
        item.godot_package_id
        for item in load_species_catalog(root=PROJECT_ROOT / "config").definitions
        if item.resolvable
    )
    raw_species_ids = manifest.get("species_package_ids")
    if not isinstance(raw_species_ids, list) or any(
        not isinstance(item, str) for item in raw_species_ids
    ):
        return False
    if tuple(sorted(raw_species_ids)) != tuple(sorted(expected_species)):
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


def _write_manifest(
    directory: Path,
    godot_version: str,
    fingerprint: str,
    species_catalog_digest: str,
    species_package_ids: tuple[str, ...],
) -> None:
    """Write a typed-by-shape artifact digest for the single executable."""
    entry = directory / ENTRY_NAME
    manifest: Dict[str, object] = {
        "schema_version": 2,
        "godot_version": godot_version,
        "preset": PRESET_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": ENTRY_NAME,
        "source_fingerprint": fingerprint,
        "species_catalog_digest": species_catalog_digest,
        "species_package_ids": list(species_package_ids),
        "export_boundary": export_boundary_manifest(),
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
