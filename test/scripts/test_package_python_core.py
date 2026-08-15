"""Release packaging contracts for frozen Core and management CLI executables."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import pytest

from scripts import package_python_core
from test.support.paths import PROJECT_ROOT


def test_source_core_entrypoint_remains_the_service_script() -> None:
    # Given: the source-tree Core used before a native freeze exists.
    source_entrypoint = PROJECT_ROOT / "scripts" / "serve.py"

    # When: its public service contract is inspected.
    source = source_entrypoint.read_text(encoding="utf-8")

    # Then: the freezer has a stable FastAPI service entrypoint to package.
    assert "def main():" in source
    assert '"/api/health"' in (
        PROJECT_ROOT / "app" / "interfaces" / "api" / "app.py"
    ).read_text(encoding="utf-8")


def test_freeze_core_builds_only_on_its_native_target(tmp_path: Path) -> None:
    # Given: a Darwin runner and a requested Darwin Core output.
    commands: list[Sequence[str]] = []

    # When: the Core freezer is prepared.
    artifact = package_python_core.freeze_core(
        target="darwin-arm64",
        output_dir=tmp_path,
        host_target="darwin-arm64",
        command_runner=commands.append,
    )

    # Then: PyInstaller receives the source service and emits the target name.
    assert artifact == tmp_path / "ElfieNestCore"
    assert commands == [
        (
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--hidden-import",
            "app.bootstrap.api",
            "--name",
            "ElfieNestCore",
            "--distpath",
            str(tmp_path),
            "--workpath",
            str(tmp_path.parent / "pyinstaller-work"),
            "--specpath",
            str(tmp_path.parent / "pyinstaller-spec"),
            str(PROJECT_ROOT / "scripts" / "serve.py"),
        )
    ]


def test_freeze_core_rejects_a_cross_platform_request(tmp_path: Path) -> None:
    # Given: a macOS runner cannot produce a Windows executable.
    calls: list[Sequence[str]] = []

    # When: a cross-platform freeze is requested.
    with pytest.raises(package_python_core.NativeTargetRequiredError):
        package_python_core.freeze_core(
            target="win32-x64",
            output_dir=tmp_path,
            host_target="darwin-arm64",
            command_runner=calls.append,
        )

    # Then: no packager process starts.
    assert calls == []


def test_freeze_cli_builds_a_checkout_independent_management_executable(
    tmp_path: Path,
) -> None:
    # Given: a native target runner and the product CLI entrypoint.
    commands: list[Sequence[str]] = []

    # When: release preparation freezes the CLI beside its target Core.
    artifact = package_python_core.freeze_cli(
        target="darwin-arm64",
        output_dir=tmp_path,
        host_target="darwin-arm64",
        command_runner=commands.append,
    )

    # Then: the native executable is built from the CLI entrypoint, not a checkout wrapper.
    assert artifact == tmp_path / "ElfieNestCli"
    assert commands[0][-1] == str(PROJECT_ROOT / "scripts" / "elfienest.py")
    assert "ElfieNestCli" in commands[0]
