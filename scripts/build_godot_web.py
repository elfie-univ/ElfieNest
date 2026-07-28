#!/usr/bin/env python3
"""Export the Godot project as ElfieNest's bundled Web Runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GODOT_PROJECT = PROJECT_ROOT / "godot_project"
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "components" / "godot-web"
PRESET_NAME = "Web"
ENTRY_NAME = "elfienest.html"
REQUIRED_SUFFIXES = (".html", ".js", ".wasm", ".pck")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ElfieNest Godot Web Runtime")
    parser.add_argument("--godot", type=Path, help="Godot 4 executable")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="only check existing artifacts")
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="export only when the Web Runtime is missing or stale",
    )
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="allow a Godot version different from the project version (not recommended for release)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    if args.check:
        return _print_bundle_check(output)
    if args.ensure and runtime_is_current(output):
        print(f"✅ Godot Web Runtime is up-to-date: {output / ENTRY_NAME}")
        return 0

    return _export_runtime(output, args.godot, args.allow_version_mismatch)


def _export_runtime(
    output: Path,
    explicit_binary: Optional[Path],
    allow_version_mismatch: bool,
) -> int:
    """Export the Godot Runtime and atomically replace the current bundle after validation."""
    binary = _find_godot(explicit_binary)
    if binary is None:
        print("❌ Godot 4 was not found. Specify the build tool with --godot or GODOT_BIN.")
        return 2
    required_version = _project_version()
    actual_version = _godot_version(binary)
    if (
        required_version
        and actual_version
        and required_version != actual_version
        and not allow_version_mismatch
    ):
        print(
            f"❌ Project requires Godot {required_version}; current build tool is {actual_version}."
        )
        print("   Release builds must use matching Godot and Web Export Templates versions.")
        return 2

    with _build_lock(output):
        if runtime_is_current(output):
            print(f"✅ Godot Web Runtime was updated by another process: {output / ENTRY_NAME}")
            return 0
        return _export_runtime_locked(output, binary, actual_version, required_version)


def _export_runtime_locked(
    output: Path,
    binary: Path,
    actual_version: Optional[str],
    required_version: Optional[str],
) -> int:
    """Run one real Godot export while holding the exclusive lock."""
    staging = output.parent / f".{output.name}.staging"
    previous = output.parent / f".{output.name}.previous"
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
    print(f"🔨 Building Web Runtime with Godot {actual_version or 'unknown'}...")
    result = subprocess.run(command, cwd=GODOT_PROJECT, check=False)
    if result.returncode != 0:
        shutil.rmtree(staging, ignore_errors=True)
        print("❌ Godot Web export failed. Confirm that matching Web Export Templates are installed.")
        _print_template_hint(required_version or actual_version or "matching")
        return result.returncode or 1

    missing = _missing_artifacts(staging)
    if missing:
        shutil.rmtree(staging, ignore_errors=True)
        print("❌ Export command completed, but artifacts are incomplete: " + ", ".join(missing))
        return 1

    _write_manifest(staging, actual_version or "unknown", current_source_fingerprint())
    shutil.rmtree(previous, ignore_errors=True)
    if output.exists():
        output.replace(previous)
    staging.replace(output)
    shutil.rmtree(previous, ignore_errors=True)
    print(f"✅ Godot Web Runtime generated: {output}")
    print(f"   Entry: {output / ENTRY_NAME}")
    return 0


def _print_bundle_check(output: Path) -> int:
    missing = _missing_artifacts(output)
    manifest = output / "build-manifest.json"
    if not manifest.is_file():
        missing.append("build-manifest.json")
    if missing:
        print(f"❌ Godot Web Runtime is incomplete: {', '.join(missing)}")
        print("   Run: ./elfienest.sh build-godot-web")
        return 1
    print(f"✅ Godot Web Runtime is available: {output / ENTRY_NAME}")
    return 0


def _missing_artifacts(directory: Path) -> List[str]:
    files = tuple(directory.glob("elfienest.*")) if directory.is_dir() else ()
    suffixes = {path.suffix for path in files if path.is_file()}
    return [suffix for suffix in REQUIRED_SUFFIXES if suffix not in suffixes]


def _write_manifest(
    directory: Path, godot_version: str, source_fingerprint: str
) -> None:
    files: Dict[str, Dict[str, object]] = {}
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[path.name] = {"bytes": path.stat().st_size, "sha256": digest}
    manifest = {
        "schema_version": 1,
        "godot_version": godot_version,
        "preset": PRESET_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": ENTRY_NAME,
        "source_fingerprint": source_fingerprint,
        "files": files,
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def current_source_fingerprint() -> str:
    """Return a fingerprint of Godot source files that affect Web export, excluding editor cache."""
    digest = hashlib.sha256()
    if not GODOT_PROJECT.is_dir():
        return digest.hexdigest()
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
    """Check bundle integrity and whether the manifest matches current Godot source."""
    missing = _missing_artifacts(output)
    manifest_path = output / "build-manifest.json"
    if missing or not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(manifest, dict):
        return False
    if manifest.get("source_fingerprint") != current_source_fingerprint():
        return False
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        return False
    for filename, metadata in expected_files.items():
        if not isinstance(filename, str) or not isinstance(metadata, dict):
            return False
        path = output / filename
        if not path.is_file():
            return False
        if metadata.get("bytes") != path.stat().st_size:
            return False
        if metadata.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            return False
    return True


class _build_lock:
    """File lock allowing only one Godot Web export per source tree."""

    def __init__(self, output: Path) -> None:
        self._path = output.parent / f".{output.name}.lock"
        self._fd: Optional[int] = None

    def __enter__(self) -> _build_lock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 120
        while self._fd is None:
            try:
                self._fd = os.open(
                    str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                os.write(self._fd, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"Godot Web Runtime build lock timeout: {self._path}"
                    ) from None
                time.sleep(0.2)
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass


def _find_godot(explicit: Optional[Path]) -> Optional[Path]:
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    environment_binary = os.environ.get("GODOT_BIN", "").strip()
    if environment_binary:
        candidates.append(Path(environment_binary).expanduser())
    for name in ("godot4", "godot", "Godot", "godot4.exe", "godot.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if platform.system() == "Darwin":
        candidates.extend(
            [
                Path("/Applications/Godot.app/Contents/MacOS/Godot"),
                Path.home() / "Applications/Godot.app/Contents/MacOS/Godot",
                Path.home() / "Downloads/Godot.app/Contents/MacOS/Godot",
            ]
        )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def _project_version() -> Optional[str]:
    text = (GODOT_PROJECT / "project.godot").read_text(encoding="utf-8")
    match = re.search(r'config/features=PackedStringArray\("(\d+\.\d+)"', text)
    return match.group(1) if match else None


def _godot_version(binary: Path) -> Optional[str]:
    result = subprocess.run(
        [str(binary), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    match = re.search(r"(\d+\.\d+)", result.stdout + result.stderr)
    return match.group(1) if match else None


def _print_template_hint(version: str) -> None:
    print(f"   Open in Godot {version}: Editor > Manage Export Templates.")
    print("   Install the official Export Templates, then rerun the build command.")


if __name__ == "__main__":
    raise SystemExit(main())
