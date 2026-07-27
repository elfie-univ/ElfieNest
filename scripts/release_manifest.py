"""Independently verify the complete runtime manifest before Electron packaging."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Final, Mapping, Tuple

from scripts import package_python_core

REQUIRED_WEB_FILES: Final[Tuple[str, ...]] = (
    "web/index.html",
    "web/manifest.json",
)
REQUIRED_GODOT_FILES: Final[Tuple[str, ...]] = (
    "godot-web/elfienest.html",
    "godot-web/elfienest.js",
    "godot-web/elfienest.wasm",
    "godot-web/elfienest.pck",
)


class ReleaseResourceManifestError(RuntimeError):
    """Raised when a staged runtime does not exactly match its signed file manifest."""


def validate_release_resources(resources: Path) -> None:
    """Verify required target files, manifest shape, hashes, and complete file coverage."""
    manifest_path = resources / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseResourceManifestError(
            f"release-manifest-unreadable path={manifest_path}"
        ) from error
    if not isinstance(payload, dict):
        raise ReleaseResourceManifestError("release-manifest-root-invalid")
    target = payload.get("target")
    if not isinstance(target, str) or target not in package_python_core.TARGETS:
        raise ReleaseResourceManifestError("release-manifest-target-invalid")
    if payload.get("schema_version") != 1:
        raise ReleaseResourceManifestError("release-manifest-schema-invalid")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ReleaseResourceManifestError("release-manifest-files-invalid")
    expected = _parse_entries(files)
    required = _required_paths(target)
    missing = sorted(required.difference(expected))
    if missing:
        raise ReleaseResourceManifestError(
            f"release-manifest-required-files-missing paths={','.join(missing)}"
        )
    actual = _actual_paths(resources)
    if actual != set(expected):
        raise ReleaseResourceManifestError("release-manifest-file-set-mismatch")
    for relative, entry in expected.items():
        path = _safe_resource_path(resources, relative)
        if not path.is_file():
            raise ReleaseResourceManifestError(
                f"release-manifest-file-missing path={relative}"
            )
        data = path.read_bytes()
        if len(data) != entry[0] or hashlib.sha256(data).hexdigest() != entry[1]:
            raise ReleaseResourceManifestError(
                f"release-manifest-file-checksum-mismatch path={relative}"
            )


def _parse_entries(files: Dict[str, object]) -> Mapping[str, Tuple[int, str]]:
    """Parse JSON file records into the minimal checked runtime contract."""
    entries: Dict[str, Tuple[int, str]] = {}
    for relative, raw_entry in files.items():
        if not isinstance(relative, str) or not isinstance(raw_entry, dict):
            raise ReleaseResourceManifestError("release-manifest-entry-invalid")
        size = raw_entry.get("size")
        checksum = raw_entry.get("sha256")
        if not isinstance(size, int) or size < 0:
            raise ReleaseResourceManifestError(
                f"release-manifest-file-size-invalid path={relative}"
            )
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
        ):
            raise ReleaseResourceManifestError(
                f"release-manifest-file-sha256-invalid path={relative}"
            )
        _safe_relative_path(relative)
        entries[relative] = (size, checksum)
    return entries


def _required_paths(target: str) -> set[str]:
    """Return runtime paths that every target package must contain."""
    executable_suffix = ".exe" if target == "win32-x64" else ""
    return {
        *REQUIRED_WEB_FILES,
        *REQUIRED_GODOT_FILES,
        f"python-core/ElfieNestCore{executable_suffix}",
        f"management-cli/ElfieNestCli{executable_suffix}",
    }


def _actual_paths(resources: Path) -> set[str]:
    """Enumerate every staged runtime file except the manifest itself."""
    return {
        path.relative_to(resources).as_posix()
        for path in resources.rglob("*")
        if path.is_file() and path.relative_to(resources).as_posix() != "manifest.json"
    }


def _safe_resource_path(resources: Path, relative: str) -> Path:
    """Resolve one manifest entry while rejecting traversal out of staging."""
    _safe_relative_path(relative)
    return resources / relative


def _safe_relative_path(relative: str) -> None:
    """Reject absolute and parent-traversal manifest paths."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ReleaseResourceManifestError(
            f"release-manifest-path-unsafe path={relative}"
        )
