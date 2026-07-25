"""Release packaging contracts for the frozen Core and Ollama sidecar."""

from __future__ import annotations

import hashlib
import os
import subprocess
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
            "--name",
            "ElfieNestCore",
            "--add-data",
            f"{PROJECT_ROOT / 'app' / 'interfaces' / 'web' / 'static'}{os.pathsep}app/interfaces/web/static",
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


def test_ollama_provenance_pins_every_release_target_and_license() -> None:
    # Given: the checked-in sidecar source registry.
    registry = package_python_core.load_ollama_sources()

    # When: each supported desktop target resolves its source contract.
    sources = [registry.for_target(target) for target in package_python_core.TARGETS]

    # Then: every source is immutable, official, and carries a local license notice.
    assert {source.target for source in sources} == set(package_python_core.TARGETS)
    assert all(source.url.startswith("https://github.com/ollama/ollama/releases/") for source in sources)
    assert all(len(source.sha256) == 64 for source in sources)
    assert all((PROJECT_ROOT / source.license_notice).is_file() for source in sources)
    assert {source.version for source in sources} == {"0.32.3"}


def test_verify_ollama_source_rejects_checksum_mismatch_before_staging(
    tmp_path: Path,
) -> None:
    # Given: a source file whose bytes do not match its requested provenance.
    source = tmp_path / "ollama-darwin.tgz"
    source.write_bytes(b"not an Ollama release archive")
    expected_sha256 = hashlib.sha256(b"trusted bytes").hexdigest()
    provenance = package_python_core.OllamaSource(
        target="darwin-arm64",
        version="0.32.3",
        url="https://github.com/ollama/ollama/releases/download/v0.32.3/ollama-darwin.tgz",
        filename=source.name,
        sha256=expected_sha256,
        license_notice="desktop/packaging/third_party/ollama/LICENSE",
    )

    # When: staging asks to verify the downloaded source.
    with pytest.raises(package_python_core.OllamaSourceChecksumError):
        package_python_core.verify_ollama_source(source, provenance)

    # Then: no derived sidecar or model data is created.
    assert list(tmp_path.iterdir()) == [source]


def test_verify_ollama_cli_returns_nonzero_for_an_intentional_checksum_mismatch(
    tmp_path: Path,
) -> None:
    # Given: a file with a valid target filename but incorrect release bytes.
    source = tmp_path / "ollama-darwin.tgz"
    source.write_bytes(b"tampered")

    # When: the source verification command is invoked.
    result = subprocess.run(
        [
            sys.executable,
            "scripts/package_python_core.py",
            "verify-ollama",
            "--target",
            "darwin-arm64",
            "--source",
            str(source),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: it refuses the bytes before a later staging task can consume them.
    assert result.returncode == 1
    assert "ollama-source-checksum-mismatch" in result.stderr
