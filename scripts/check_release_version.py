#!/usr/bin/env python3
"""Check that application-facing release metadata matches the project version."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
PYPROJECT_PATH: Final = PROJECT_ROOT / "pyproject.toml"
DESKTOP_MANIFEST_PATH: Final = (
    PROJECT_ROOT / "app" / "interfaces" / "desktop" / "package.json"
)
FRONTEND_MANIFEST_PATH: Final = (
    PROJECT_ROOT / "app" / "interfaces" / "web" / "frontend" / "package.json"
)
VERSION_PATTERN: Final = re.compile(
    r'^version\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE
)


class ReleaseVersionError(RuntimeError):
    """Raised when application release metadata is unavailable or inconsistent."""


def parse_args() -> argparse.Namespace:
    """Parse optional manifest overrides used by release verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-manifest", type=Path, default=DESKTOP_MANIFEST_PATH)
    parser.add_argument(
        "--frontend-manifest", type=Path, default=FRONTEND_MANIFEST_PATH
    )
    return parser.parse_args()


def project_version() -> str:
    """Return the PEP 621 application version declared in pyproject.toml."""
    match = VERSION_PATTERN.search(PYPROJECT_PATH.read_text(encoding="utf-8"))
    if match is None:
        raise ReleaseVersionError(f"release-version-missing path={PYPROJECT_PATH}")
    return match.group("version")


def manifest_version(path: Path) -> str:
    """Return the string version declared by one Node package manifest."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseVersionError(f"release-version-unreadable path={path}") from error
    version = payload.get("version")
    if not isinstance(version, str) or version.strip() == "":
        raise ReleaseVersionError(f"release-version-missing path={path}")
    return version


def check_versions(desktop_manifest: Path, frontend_manifest: Path) -> str:
    """Return the canonical version or raise when a manifest differs."""
    expected = project_version()
    actual_versions = (
        ("desktop", desktop_manifest, manifest_version(desktop_manifest)),
        ("frontend", frontend_manifest, manifest_version(frontend_manifest)),
    )
    for component, path, actual in actual_versions:
        if actual != expected:
            raise ReleaseVersionError(
                "release-version-mismatch "
                f"component={component} path={path} expected={expected} actual={actual}"
            )
    return expected


def main() -> int:
    """Execute the repository release-version consistency check."""
    args = parse_args()
    try:
        version = check_versions(args.desktop_manifest, args.frontend_manifest)
    except ReleaseVersionError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"release-version-ok version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
