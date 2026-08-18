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

from infrastructure.godot.artifacts.export_boundary import export_boundary_manifest
from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationRunner,
    SpeciesPackageValidationError,
    validate_source_species_packages,
)
from infrastructure.persistence.configuration.species import load_species_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GODOT_PROJECT = PROJECT_ROOT / "godot_project"
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "components" / "godot-web"
GODOT_WEB_DIAGNOSTIC_LOG = PROJECT_ROOT / "build" / "logs" / "godot-web-build.log"
PRESET_NAME = "Web"
ENTRY_NAME = "elfienest.html"
REQUIRED_SUFFIXES = (".html", ".js", ".wasm", ".pck")
LAN_HTTP_COMPATIBILITY_VERSION = "lan-http-v2"
LAN_HTTP_COMPATIBILITY_MARKER = "elfienest:lan-http-compatibility"
_SECURE_CONTEXT_FEATURE = "Secure Context - Check web server configuration (use HTTPS)"
_MISSING_FEATURES_STATEMENT = (
    "\tconst missing = Engine.getMissingFeatures({\n"
    "\t\tthreads: GODOT_THREADS_ENABLED,\n"
    "\t});"
)
_LAN_HTTP_COMPATIBILITY_SCRIPT = """// elfienest:lan-http-compatibility
// Godot's Web export requires this check even for the single-threaded observer.
// The service access policy limits this page to the explicitly enabled LAN.
function isPrivateLanHttpOrigin() {
\tif (window.location.protocol !== 'http:') return false;
\tconst octets = window.location.hostname.split('.');
\tif (octets.length !== 4 || octets.some((octet) => !/^\\d+$/.test(octet))) return false;
\tconst values = octets.map(Number);
\tif (values.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) return false;
\tconst [first, second] = values;
\treturn first === 127 || first === 10 || (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 168);
}
const ELFIE_NEST_LAN_HTTP = isPrivateLanHttpOrigin();
if (ELFIE_NEST_LAN_HTTP && window.AudioContext && !('audioWorklet' in window.AudioContext.prototype)) {
\tObject.defineProperty(window.AudioContext.prototype, 'audioWorklet', {
\t\tconfigurable: true,
\t\tget: () => ({ addModule: () => Promise.resolve() }),
\t});
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the ElfieNest Godot Web Runtime"
    )
    parser.add_argument("--godot", type=Path, help="Godot 4 executable")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check", action="store_true", help="only check existing artifacts"
    )
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


def main(*, godot_runner: GodotSpeciesValidationRunner | None = None) -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    if args.check:
        return _print_bundle_check(output)
    if args.ensure and runtime_is_current(output):
        print(f"✅ Godot Web Runtime is up-to-date: {output / ENTRY_NAME}")
        return 0

    return _export_runtime(
        output,
        args.godot,
        args.allow_version_mismatch,
        godot_runner=godot_runner,
    )


def _export_runtime(
    output: Path,
    explicit_binary: Optional[Path],
    allow_version_mismatch: bool,
    *,
    godot_runner: GodotSpeciesValidationRunner | None,
) -> int:
    """Export the Godot Runtime and atomically replace the current bundle after validation."""
    binary = _find_godot(explicit_binary)
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
        and not allow_version_mismatch
    ):
        print(
            f"❌ Project requires Godot {required_version}; current build tool is {actual_version}."
        )
        print(
            "   Release builds must use matching Godot and Web Export Templates versions."
        )
        return 2

    if godot_runner is None:
        print("❌ Godot Web build requires an injected species validation runner.")
        return 1
    try:
        species_package_ids = validate_source_species_packages(
            config_root=PROJECT_ROOT / "config",
            godot_project=GODOT_PROJECT,
            godot_runner=godot_runner,
            godot_binary=binary,
        )
    except SpeciesPackageValidationError as error:
        print(f"❌ Species package validation failed: {error}")
        _report_species_validation_failure(error, binary)
        return 1

    with _build_lock(output):
        if runtime_is_current(output):
            print(
                f"✅ Godot Web Runtime was updated by another process: {output / ENTRY_NAME}"
            )
            return 0
        return _export_runtime_locked(
            output,
            binary,
            actual_version,
            required_version,
            species_package_ids,
        )


def _export_runtime_locked(
    output: Path,
    binary: Path,
    actual_version: Optional[str],
    required_version: Optional[str],
    species_package_ids: tuple[str, ...],
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
        print(
            "❌ Godot Web export failed. Confirm that matching Web Export Templates are installed."
        )
        _print_template_hint(required_version or actual_version or "matching")
        return result.returncode or 1

    patch_web_entry_for_lan_http(entry)

    missing = _missing_artifacts(staging)
    if missing:
        shutil.rmtree(staging, ignore_errors=True)
        print(
            "❌ Export command completed, but artifacts are incomplete: "
            + ", ".join(missing)
        )
        return 1

    _write_manifest(
        staging,
        actual_version or "unknown",
        current_source_fingerprint(),
        current_species_catalog_digest(),
        species_package_ids,
    )
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


def _report_species_validation_failure(
    error: SpeciesPackageValidationError,
    godot_binary: Path,
) -> None:
    """Expose and persist the Godot process output instead of reducing it to an exit code."""
    timestamp = datetime.now(timezone.utc).isoformat()
    diagnostic = (
        f"=== ElfieNest Godot Web diagnostic {timestamp} ===\n"
        f"phase={error.phase}\n"
        f"godot_binary={godot_binary}\n"
        f"godot_project={GODOT_PROJECT}\n"
        "validation_script=scripts/test/test_species_catalog.gd\n"
        f"failure={error}\n"
        "stdout:\n"
        f"{error.stdout.rstrip() or '(empty)'}\n"
        "stderr:\n"
        f"{error.stderr.rstrip() or '(empty)'}\n"
    )
    print("   ┌─ Godot validation output ─────────────────────────────")
    print(diagnostic.rstrip())
    print("   └──────────────────────────────────────────────────────")
    try:
        GODOT_WEB_DIAGNOSTIC_LOG.parent.mkdir(parents=True, exist_ok=True)
        with GODOT_WEB_DIAGNOSTIC_LOG.open("a", encoding="utf-8") as stream:
            stream.write(diagnostic)
            stream.write("\n")
    except OSError as log_error:
        print(f"   ⚠️ Could not write diagnostic log: {log_error}")
    else:
        print(f"   📄 Full diagnostic log: {GODOT_WEB_DIAGNOSTIC_LOG}")


def _missing_artifacts(directory: Path) -> List[str]:
    files = tuple(directory.glob("elfienest.*")) if directory.is_dir() else ()
    suffixes = {path.suffix for path in files if path.is_file()}
    return [suffix for suffix in REQUIRED_SUFFIXES if suffix not in suffixes]


def _write_manifest(
    directory: Path,
    godot_version: str,
    source_fingerprint: str,
    species_catalog_digest: str,
    species_package_ids: tuple[str, ...],
) -> None:
    files: Dict[str, Dict[str, object]] = {}
    for path in sorted(item for item in directory.iterdir() if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[path.name] = {"bytes": path.stat().st_size, "sha256": digest}
    manifest = {
        "schema_version": 2,
        "godot_version": godot_version,
        "preset": PRESET_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry": ENTRY_NAME,
        "source_fingerprint": source_fingerprint,
        "species_catalog_digest": species_catalog_digest,
        "species_package_ids": list(species_package_ids),
        "export_boundary": export_boundary_manifest(),
        "files": files,
    }
    (directory / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def current_source_fingerprint() -> str:
    """Return a fingerprint of the Godot source and Web entry compatibility version."""
    digest = hashlib.sha256()
    digest.update(LAN_HTTP_COMPATIBILITY_VERSION.encode("utf-8"))
    digest.update(b"\0")
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


def current_species_catalog_digest() -> str:
    """Return the bundled species catalog digest paired with this export."""
    return load_species_catalog(root=PROJECT_ROOT / "config").digest


def patch_web_entry_for_lan_http(entry: Path) -> None:
    """Make the single-threaded Godot observer start on an explicitly enabled LAN HTTP origin."""
    text = entry.read_text(encoding="utf-8")
    if LAN_HTTP_COMPATIBILITY_MARKER in text:
        return
    if _MISSING_FEATURES_STATEMENT not in text:
        raise RuntimeError(
            f"Godot Web entry format is unsupported; cannot patch {entry}"
        )
    config_marker = "const GODOT_CONFIG ="
    if config_marker not in text:
        raise RuntimeError(
            f"Godot Web entry is missing its configuration block; cannot patch {entry}"
        )
    text = text.replace(
        config_marker,
        f"{_LAN_HTTP_COMPATIBILITY_SCRIPT}\n{config_marker}",
        1,
    )
    text = text.replace(
        _MISSING_FEATURES_STATEMENT,
        _MISSING_FEATURES_STATEMENT[:-1]
        + f".filter((feature) => !(ELFIE_NEST_LAN_HTTP && feature === '{_SECURE_CONTEXT_FEATURE}'));",
        1,
    )
    entry.write_text(text, encoding="utf-8")


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


class GodotWebBuildAdapter:
    """Infrastructure implementation of lifecycle-owned Godot Web preparation."""

    def __init__(self, *, godot_runner: GodotSpeciesValidationRunner) -> None:
        self._godot_runner = godot_runner

    def prepare(self, runtime_mode: str, *, is_frozen: bool) -> bool:
        if runtime_mode == "release" and is_frozen:
            return True
        if runtime_mode == "development":
            if runtime_is_current(DEFAULT_OUTPUT):
                return True
            return (
                _export_runtime(
                    DEFAULT_OUTPUT,
                    None,
                    False,
                    godot_runner=self._godot_runner,
                )
                == 0
            )
        return _print_bundle_check(DEFAULT_OUTPUT) == 0


if __name__ == "__main__":
    raise SystemExit(main())
