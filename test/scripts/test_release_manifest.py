"""Independent verification contracts for assembled desktop runtime resources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import release_manifest


def test_manifest_validation_rejects_a_manifest_that_omits_required_godot_files(
    tmp_path: Path,
) -> None:
    # Given: a staging root whose manifest covers only a React shell.
    resources = tmp_path / "resources"
    shell = resources / "web" / "index.html"
    shell.parent.mkdir(parents=True)
    shell.write_bytes(b"shell")
    payload = {
        "schema_version": 1,
        "application_version": "0.1.0",
        "target": "darwin-arm64",
        "files": {
            "web/index.html": {
                "size": len(b"shell"),
                "sha256": hashlib.sha256(b"shell").hexdigest(),
            }
        },
    }
    (resources / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    # When/Then: an incomplete product runtime cannot reach electron packaging.
    with pytest.raises(release_manifest.ReleaseResourceManifestError, match="godot-web"):
        release_manifest.validate_release_resources(resources)
