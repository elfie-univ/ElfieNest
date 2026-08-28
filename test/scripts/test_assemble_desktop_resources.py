"""Contracts for assembling one verified desktop resource tree."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.internal.build import assemble_desktop_resources


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_web_bundle(root: Path) -> None:
    for name in ("index.html", "manifest.json"):
        _write_file(root / name, name.encode("utf-8"))
    _write_file(root / "assets" / "app.js", b"web-asset")


def _write_godot_bundle(root: Path) -> None:
    for suffix in ("html", "js", "wasm", "pck"):
        _write_file(root / f"elfienest.{suffix}", suffix.encode("utf-8"))


def _write_godot_dedicated_bundle(root: Path) -> None:
    _write_file(root / "ElfieNestRuntime", b"dedicated")
    (root / "ElfieNestRuntime").chmod(0o755)
    _write_file(root / "build-manifest.json", b"{}")


def _write_config_bundle(root: Path) -> None:
    _write_file(root / "app" / "system-defaults.yaml", b"version: 1\nsystem: {}\n")
    shutil.copytree(
        assemble_desktop_resources.DEFAULT_CONFIG_SOURCE / "species",
        root / "species",
    )


def test_assemble_resources_copies_one_target_and_writes_a_manifest(
    tmp_path: Path,
) -> None:
    # Given: target-native Core and CLI executables plus the remaining verified inputs.
    target = "darwin-x64"
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    config = tmp_path / "config"
    _write_web_bundle(web)
    _write_godot_bundle(godot)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    _write_config_bundle(config)

    # When: staging assembles only that target.
    resources = assemble_desktop_resources.assemble_resources(
        target=target,
        output_root=tmp_path / "staging",
        web_source=web,
        godot_source=godot,
        core_source=core,
        cli_source=cli,
        config_source=config,
        application_version="0.1.0",
        source_revision="a" * 40,
    )

    # Then: the flat Electron resource root contains every runtime component.
    assert resources == tmp_path / "staging" / target / "resources"
    assert (resources / "web" / "assets" / "app.js").read_bytes() == b"web-asset"
    assert (resources / "godot-web" / "elfienest.wasm").read_bytes() == b"wasm"
    assert (resources / "python-core" / "ElfieNestCore").read_bytes() == b"core"
    assert (resources / "management-cli" / "ElfieNestCli").read_bytes() == b"cli"
    assert (resources / "config" / "app" / "system-defaults.yaml").is_file()
    assert not (resources / "ollama").exists()
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["application_version"] == "0.1.0"
    assert manifest["schema_version"] == 2
    assert manifest["source_revision"] == "a" * 40
    assert manifest["target"] == target
    assert "web/assets/app.js" in manifest["files"]
    assert "web/manifest.json" in manifest["files"]
    assert not any(path.startswith("ollama/") for path in manifest["files"])


def test_assemble_resources_requires_the_single_product_react_shell(
    tmp_path: Path,
) -> None:
    # Given: a build with a Vite manifest but no index.html product shell.
    target = "darwin-x64"
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    config = tmp_path / "config"
    _write_file(web / "manifest.json", b"{}")
    _write_godot_bundle(godot)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    _write_config_bundle(config)

    # When/Then: packaging refuses a server-routed SPA without its one shell.
    with pytest.raises(
        assemble_desktop_resources.ResourceAssemblyError,
        match=r"component=web missing=index.html",
    ):
        assemble_desktop_resources.assemble_resources(
            target=target,
            output_root=tmp_path / "staging",
            web_source=web,
            godot_source=godot,
            core_source=core,
            cli_source=cli,
            config_source=config,
            application_version="0.1.0",
            source_revision="a" * 40,
        )


def test_linux_assembly_packages_the_dedicated_world_authority(
    tmp_path: Path,
) -> None:
    # Given: all Linux package inputs, including the headless Godot export.
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    dedicated = tmp_path / "godot-linux-dedicated"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    config = tmp_path / "config"
    _write_web_bundle(web)
    _write_godot_bundle(godot)
    _write_godot_dedicated_bundle(dedicated)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    _write_config_bundle(config)

    # When: Linux resources are assembled for the DEB.
    resources = assemble_desktop_resources.assemble_resources(
        target="linux-x64",
        output_root=tmp_path / "staging",
        web_source=web,
        godot_source=godot,
        godot_dedicated_source=dedicated,
        core_source=core,
        cli_source=cli,
        config_source=config,
        application_version="0.1.0",
        source_revision="a" * 40,
    )

    # Then: the exact executable and its export provenance enter the signed resources.
    runtime = resources / "godot-linux-dedicated" / "ElfieNestRuntime"
    assert runtime.read_bytes() == b"dedicated"
    assert runtime.stat().st_mode & 0o111
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    assert "godot-linux-dedicated/ElfieNestRuntime" in manifest["files"]
    assert "godot-linux-dedicated/build-manifest.json" in manifest["files"]


def test_linux_assembly_rejects_a_missing_dedicated_world_authority(
    tmp_path: Path,
) -> None:
    # Given: otherwise complete Linux inputs without a dedicated Godot bundle.
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    config = tmp_path / "config"
    _write_web_bundle(web)
    _write_godot_bundle(godot)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    _write_config_bundle(config)

    # When/Then: an installer cannot be assembled without its World authority.
    with pytest.raises(
        assemble_desktop_resources.ResourceAssemblyError,
        match="component=godot-linux-dedicated",
    ):
        assemble_desktop_resources.assemble_resources(
            target="linux-x64",
            output_root=tmp_path / "staging",
            web_source=web,
            godot_source=godot,
            core_source=core,
            cli_source=cli,
            config_source=config,
            application_version="0.1.0",
            source_revision="a" * 40,
        )
