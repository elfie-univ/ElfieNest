from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test.support.paths import PROJECT_ROOT

VERSION_CHECK = PROJECT_ROOT / "scripts" / "quality" / "checks" / "release_version.py"


def test_release_version_check_accepts_repository_metadata() -> None:
    # Given: the repository's release metadata.

    # When: the release version check is executed.
    result = subprocess.run(
        [sys.executable, str(VERSION_CHECK)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: every application-facing manifest agrees with pyproject.toml.
    assert result.returncode == 0, result.stderr
    assert "release-version-ok version=0.1.0-beta.2" in result.stdout


def test_release_version_check_rejects_mismatched_frontend_manifest(
    tmp_path: Path,
) -> None:
    # Given: a copied frontend manifest with a different application version.
    copied_manifest = tmp_path / "package.json"
    manifest = json.loads(
        (PROJECT_ROOT / "app/interfaces/web/frontend/package.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["version"] = "0.1.1"
    copied_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    # When: the release version check reads that copied manifest.
    result = subprocess.run(
        [
            sys.executable,
            str(VERSION_CHECK),
            "--frontend-manifest",
            str(copied_manifest),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: it exits nonzero with a machine-readable mismatch diagnostic.
    assert result.returncode != 0
    assert "release-version-mismatch" in result.stderr
    assert "0.1.1" in result.stderr
