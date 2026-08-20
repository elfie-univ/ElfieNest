#!/usr/bin/env python3
"""Export the Godot project as ElfieNest's bundled Web Runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

if os.name == "nt":
    import msvcrt
else:
    import fcntl

from infrastructure.godot.artifacts.export_boundary import export_boundary_manifest
from infrastructure.godot.artifacts.species_package_validation import (
    GodotSpeciesValidationRunner,
    SpeciesPackageValidationError,
    source_species_package_ids,
    validate_source_species_packages,
)
from infrastructure.godot.runner import (
    find_godot,
    forward_output,
    godot_version,
    project_version,
    run_headless,
)
from infrastructure.persistence.configuration.species import load_species_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GODOT_PROJECT = PROJECT_ROOT / "godot_project"
DEFAULT_OUTPUT = PROJECT_ROOT / "build" / "components" / "godot-web"
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
        species_package_ids = source_species_package_ids(
            config_root=PROJECT_ROOT / "config",
            godot_project=GODOT_PROJECT,
        )
    except SpeciesPackageValidationError as error:
        print(f"❌ Species package validation failed: {error} phase={error.phase}")
        if error.stdout.strip():
            print(f"   Godot stdout:\n{error.stdout.rstrip()}")
        if error.stderr.strip():
            print(f"   Godot stderr:\n{error.stderr.rstrip()}")
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
            godot_runner,
        )


def _export_runtime_locked(
    output: Path,
    binary: Path,
    actual_version: Optional[str],
    required_version: Optional[str],
    species_package_ids: tuple[str, ...],
    godot_runner: GodotSpeciesValidationRunner,
) -> int:
    """Export, then validate the imported source before publishing the bundle."""
    staging = output.parent / f".{output.name}.staging"
    previous = output.parent / f".{output.name}.previous"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    entry = staging / ENTRY_NAME
    print(f"🔨 Building Web Runtime with Godot {actual_version or 'unknown'}...")
    result = run_headless(
        binary,
        GODOT_PROJECT,
        ("--export-release", PRESET_NAME, str(entry)),
        timeout_seconds=600.0,
        godot_version=actual_version,
        purpose="web-runtime-export",
    )
    forward_output(result)
    if result.exit_code != 0:
        shutil.rmtree(staging, ignore_errors=True)
        if result.crashed:
            print("❌ Godot crashed during Web Runtime export; no retry was attempted.")
        print(
            "❌ Godot Web export failed. Confirm that matching Web Export Templates are installed."
        )
        _print_template_hint(required_version or actual_version or "matching")
        return result.exit_code

    patch_web_entry_for_lan_http(entry)

    missing = _missing_artifacts(staging)
    if missing:
        shutil.rmtree(staging, ignore_errors=True)
        print(
            "❌ Export command completed, but artifacts are incomplete: "
            + ", ".join(missing)
        )
        return 1

    try:
        validated_species_package_ids = validate_source_species_packages(
            config_root=PROJECT_ROOT / "config",
            godot_project=GODOT_PROJECT,
            godot_runner=godot_runner,
            godot_binary=binary,
            godot_version=actual_version,
        )
    except SpeciesPackageValidationError as error:
        shutil.rmtree(staging, ignore_errors=True)
        print(f"❌ Species package validation failed: {error} phase={error.phase}")
        if error.stdout.strip():
            print(f"   Godot stdout:\n{error.stdout.rstrip()}")
        if error.stderr.strip():
            print(f"   Godot stderr:\n{error.stderr.rstrip()}")
        return 1
    if validated_species_package_ids != species_package_ids:
        shutil.rmtree(staging, ignore_errors=True)
        print(
            "❌ Species package validation changed the source package set during export."
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
    """OS-owned lock allowing only one Godot Web export per source tree."""

    def __init__(self, output: Path) -> None:
        self._path = output.parent / f".{output.name}.lock"
        self._fd: Optional[int] = None

    def __enter__(self) -> _build_lock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR, 0o600)
        if os.name != "nt":
            os.fchmod(self._fd, 0o600)
        if os.fstat(self._fd).st_size == 0:
            os.write(self._fd, b"\0")
        deadline = time.monotonic() + 120
        while not _try_acquire_build_lock(self._fd):
            if time.monotonic() >= deadline:
                os.close(self._fd)
                self._fd = None
                raise RuntimeError(
                    f"Godot Web Runtime build lock timeout: {self._path}"
                ) from None
            time.sleep(0.2)
        try:
            os.ftruncate(self._fd, 0)
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, str(os.getpid()).encode("ascii"))
        except OSError:
            _release_build_lock(self._fd)
            os.close(self._fd)
            self._fd = None
            raise
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._fd is None:
            return
        try:
            _release_build_lock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None


def _try_acquire_build_lock(descriptor: int) -> bool:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt_module = cast(Any, msvcrt)
        locking = cast(Callable[[int, int, int], None], msvcrt_module.locking)
        try:
            locking(descriptor, int(msvcrt_module.LK_NBLCK), 1)
        except OSError:
            return False
        return True
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _release_build_lock(descriptor: int) -> None:
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt_module = cast(Any, msvcrt)
        locking = cast(Callable[[int, int, int], None], msvcrt_module.locking)
        locking(descriptor, int(msvcrt_module.LK_UNLCK), 1)
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _find_godot(explicit: Optional[Path]) -> Optional[Path]:
    return find_godot(explicit)


def _project_version() -> Optional[str]:
    return project_version(GODOT_PROJECT)


def _godot_version(binary: Path) -> Optional[str]:
    return godot_version(binary)


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
