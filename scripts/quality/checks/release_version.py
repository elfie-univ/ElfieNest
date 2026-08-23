#!/usr/bin/env python3
"""Check that application-facing release metadata matches the project version."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.internal.release.version import (  # noqa: E402
    DESKTOP_MANIFEST_PATH,
    FRONTEND_MANIFEST_PATH,
    ReleaseVersionError,
    check_versions,
)


def parse_args() -> argparse.Namespace:
    """Parse optional manifest overrides used by release verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop-manifest", type=Path, default=DESKTOP_MANIFEST_PATH)
    parser.add_argument(
        "--frontend-manifest", type=Path, default=FRONTEND_MANIFEST_PATH
    )
    return parser.parse_args()


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
