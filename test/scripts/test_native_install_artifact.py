"""Native application-layout installation contracts without a source checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

from test.support.paths import PROJECT_ROOT


def _write_macos_bundle(root: Path, cli_content: bytes) -> None:
    cli = root / "Contents" / "Resources" / "management-cli" / "ElfieNestCli"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(cli_content)
    cli.chmod(0o755)


def test_macos_bundle_install_atomically_replaces_only_the_native_application(
    tmp_path: Path,
) -> None:
    # Given: an existing application and a new native bundle with its packaged CLI.
    source = tmp_path / "ElfieNest.new.app"
    destination = tmp_path / "Applications" / "ElfieNest.app"
    _write_macos_bundle(source, b"new-cli")
    _write_macos_bundle(destination, b"old-cli")

    # When: the platform installer swaps the bundle.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; install_macos_app_bundle "$2" "$3"',
            "native-install",
            str(PROJECT_ROOT / "scripts" / "native_install_artifact.sh"),
            str(source),
            str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: the installed app contains the new standalone CLI, not a checkout path.
    assert result.returncode == 0, result.stdout + result.stderr
    installed_cli = destination / "Contents" / "Resources" / "management-cli" / "ElfieNestCli"
    assert installed_cli.read_bytes() == b"new-cli"
    assert not source.is_symlink()


def test_native_cli_path_uses_the_platform_application_layout(tmp_path: Path) -> None:
    # Given: a macOS application bundle root.
    bundle = tmp_path / "Applications" / "ElfieNest.app"

    # When: the command path is resolved for that native target.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; native_cli_path darwin-arm64 "$2"',
            "native-install",
            str(PROJECT_ROOT / "scripts" / "native_install_artifact.sh"),
            str(bundle),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: it points inside the app bundle, never a source checkout directory.
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == str(
        bundle / "Contents" / "Resources" / "management-cli" / "ElfieNestCli"
    )
