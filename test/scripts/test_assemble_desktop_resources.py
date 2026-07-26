"""Contracts for assembling one verified desktop resource tree."""

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import assemble_desktop_resources, package_python_core


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


def _write_sidecar_archive(target: str, archive: Path) -> package_python_core.OllamaSource:
    executable_name = "ollama.exe" if target == "win32-x64" else "ollama"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if target == "win32-x64":
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(executable_name, b"ollama")
            bundle.writestr("lib/sidecar.dll", b"library")
    else:
        with tarfile.open(archive, "w:gz") as bundle:
            source = archive.parent / executable_name
            source.write_bytes(b"ollama")
            bundle.add(source, arcname=f"bin/{executable_name}")
    return package_python_core.OllamaSource(
        target=target,
        version="test",
        url="https://github.com/ollama/ollama/releases/download/vtest/ollama-test",
        filename=archive.name,
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        license_notice="desktop/packaging/third_party/ollama/LICENSE",
    )


def test_assemble_resources_copies_one_target_and_writes_a_manifest(tmp_path: Path) -> None:
    # Given: target-native Core and CLI executables plus the remaining verified inputs.
    target = "darwin-x64"
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    archive = tmp_path / "downloads" / "ollama-darwin.tgz"
    _write_web_bundle(web)
    _write_godot_bundle(godot)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    source = _write_sidecar_archive(target, archive)

    # When: staging assembles only that target.
    resources = assemble_desktop_resources.assemble_resources(
        target=target,
        output_root=tmp_path / "staging",
        web_source=web,
        godot_source=godot,
        core_source=core,
        cli_source=cli,
        ollama_archive=archive,
        ollama_source=source,
        application_version="0.1.0",
    )

    # Then: the flat Electron resource root contains every runtime component.
    assert resources == tmp_path / "staging" / target / "resources"
    assert (resources / "web" / "assets" / "app.js").read_bytes() == b"web-asset"
    assert (resources / "godot-web" / "elfienest.wasm").read_bytes() == b"wasm"
    assert (resources / "python-core" / "ElfieNestCore").read_bytes() == b"core"
    assert (resources / "management-cli" / "ElfieNestCli").read_bytes() == b"cli"
    assert (resources / "ollama" / "ollama").read_bytes() == b"ollama"
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["application_version"] == "0.1.0"
    assert manifest["target"] == target
    assert "web/assets/app.js" in manifest["files"]
    assert "web/manifest.json" in manifest["files"]


def test_assemble_resources_refuses_a_sidecar_with_an_invalid_checksum(tmp_path: Path) -> None:
    # Given: an altered Ollama archive and provenance for different bytes.
    archive = tmp_path / "ollama-darwin.tgz"
    archive.write_bytes(b"altered")
    source = package_python_core.OllamaSource(
        target="darwin-x64",
        version="test",
        url="https://github.com/ollama/ollama/releases/download/vtest/ollama-darwin.tgz",
        filename=archive.name,
        sha256=hashlib.sha256(b"trusted").hexdigest(),
        license_notice="desktop/packaging/third_party/ollama/LICENSE",
    )

    # When/Then: staging fails before it writes any target resource tree.
    with pytest.raises(package_python_core.OllamaSourceChecksumError):
        assemble_desktop_resources.assemble_resources(
            target="darwin-x64",
            output_root=tmp_path / "staging",
            web_source=tmp_path / "web",
            godot_source=tmp_path / "godot",
            core_source=tmp_path / "core",
            cli_source=tmp_path / "cli",
            ollama_archive=archive,
            ollama_source=source,
            application_version="0.1.0",
        )
    assert not (tmp_path / "staging" / "darwin-x64").exists()


def test_assemble_resources_requires_the_single_product_react_shell(
    tmp_path: Path,
) -> None:
    # Given: a build with a Vite manifest but no index.html product shell.
    target = "darwin-x64"
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    archive = tmp_path / "downloads" / "ollama-darwin.tgz"
    _write_file(web / "manifest.json", b"{}")
    _write_godot_bundle(godot)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    source = _write_sidecar_archive(target, archive)

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
            ollama_archive=archive,
            ollama_source=source,
            application_version="0.1.0",
        )


def test_assemble_resources_allows_a_relative_sidecar_library_symlink(
    tmp_path: Path,
) -> None:
    # Given: the macOS sidecar layout used by the official Ollama archive.
    target = "darwin-x64"
    web = tmp_path / "web"
    godot = tmp_path / "godot-web"
    core = tmp_path / "core" / "ElfieNestCore"
    cli = tmp_path / "cli" / "ElfieNestCli"
    archive = tmp_path / "downloads" / "ollama-darwin.tgz"
    _write_web_bundle(web)
    _write_godot_bundle(godot)
    _write_file(core, b"core")
    _write_file(cli, b"cli")
    archive.parent.mkdir(parents=True)
    with tarfile.open(archive, "w:gz") as bundle:
        executable = tmp_path / "ollama"
        executable.write_bytes(b"ollama")
        library = tmp_path / "libollama.1.dylib"
        library.write_bytes(b"library")
        bundle.add(executable, arcname="ollama")
        bundle.add(library, arcname="libollama.1.dylib")
        symlink = tarfile.TarInfo("libollama.dylib")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "libollama.1.dylib"
        bundle.addfile(symlink)
    source = package_python_core.OllamaSource(
        target=target,
        version="test",
        url="https://github.com/ollama/ollama/releases/download/vtest/ollama-darwin.tgz",
        filename=archive.name,
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        license_notice="desktop/packaging/third_party/ollama/LICENSE",
    )

    # When: the verified archive is staged.
    resources = assemble_desktop_resources.assemble_resources(
        target=target,
        output_root=tmp_path / "staging",
        web_source=web,
        godot_source=godot,
        core_source=core,
        cli_source=cli,
        ollama_archive=archive,
        ollama_source=source,
        application_version="0.1.0",
    )

    # Then: the executable and its required library remain available in the package.
    assert (resources / "ollama" / "ollama").is_file()
    assert (resources / "ollama" / "libollama.dylib").is_file()
