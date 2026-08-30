"""Independent verification contracts for assembled desktop runtime resources."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from scripts.internal.release import release_manifest


def _copy_species_config(resources: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    shutil.copytree(
        project_root / "config" / "species",
        resources / "config" / "species",
    )


def _copy_world_config(resources: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    target = resources / "config" / "world" / "elfaria.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_root / "config" / "world" / "elfaria.yaml", target)


def test_manifest_validation_rejects_a_manifest_that_omits_required_godot_files(
    tmp_path: Path,
) -> None:
    # Given: a staging root whose manifest covers only a React shell.
    resources = tmp_path / "resources"
    shell = resources / "web" / "index.html"
    shell.parent.mkdir(parents=True)
    shell.write_bytes(b"shell")
    payload = {
        "schema_version": 2,
        "application_version": "0.1.0",
        "source_revision": "a" * 40,
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
    with pytest.raises(
        release_manifest.ReleaseResourceManifestError, match="godot-web"
    ):
        release_manifest.validate_release_resources(resources)


def test_linux_manifest_requires_the_dedicated_world_authority() -> None:
    # Given/When: required resource paths are resolved for a Linux package.
    linux_paths = release_manifest._required_paths("linux-x64")

    # Then: both the executable and its export provenance are mandatory only there.
    assert "godot-linux-dedicated/ElfieNestRuntime" in linux_paths
    assert "godot-linux-dedicated/build-manifest.json" in linux_paths
    assert "godot-linux-dedicated/ElfieNestRuntime" not in (
        release_manifest._required_paths("darwin-arm64")
    )


def test_manifest_validation_accepts_runtime_without_a_bundled_ollama_binary(
    tmp_path: Path,
) -> None:
    # Given: every portable application resource, with no machine-level model service.
    resources = tmp_path / "resources"
    target = "darwin-arm64"
    contents = {
        "web/index.html": b"shell",
        "web/manifest.json": b"{}",
        "godot-web/elfienest.html": b"html",
        "godot-web/elfienest.js": b"js",
        "godot-web/elfienest.wasm": b"wasm",
        "godot-web/elfienest.pck": b"pck",
        "python-core/ElfieNestCore": b"core",
        "management-cli/ElfieNestCli": b"cli",
        "config/app/system-defaults.yaml": b"version: 1\nsystem: {}\n",
        "config/models/provider-catalog.yaml": b"version: 2\n",
        "config/models/model-catalog.yaml": b"version: 1\n",
        "config/tools/defaults.yaml": b"version: 1\ntools: {}\n",
        "config/brain/energy.yaml": b"version: 1\nlimits: {}\n",
        "config/brain/selfhood.yaml": b"version: 1\nbig_five: {}\n",
        "config/brain/emotion-expressions.yaml": b"version: 1\nemotions: {}\n",
        "config/brain/emotion-dynamics.yaml": b"version: 1\nchannels: {}\n",
        "config/nest/defaults.yaml": b"version: 1\nnest: {}\n",
    }
    files = {}
    for relative, data in contents.items():
        path = resources / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[relative] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    _copy_species_config(resources)
    _copy_world_config(resources)
    for path in sorted((resources / "config" / "species").rglob("*")):
        if path.is_file():
            relative = path.relative_to(resources).as_posix()
            data = path.read_bytes()
            files[relative] = {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    world_path = resources / "config" / "world" / "elfaria.yaml"
    world_data = world_path.read_bytes()
    world_relative = world_path.relative_to(resources).as_posix()
    files[world_relative] = {
        "size": len(world_data),
        "sha256": hashlib.sha256(world_data).hexdigest(),
    }
    (resources / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "application_version": "0.1.0",
                "source_revision": "a" * 40,
                "target": target,
                "files": files,
            }
        ),
        encoding="utf-8",
    )

    # When/Then: validation treats public Ollama binding as setup state, not a package file.
    release_manifest.validate_release_resources(resources)
