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
    manifest = root / "Contents" / "Resources" / "manifest.json"
    manifest.write_text('{"version":"0.1.0"}\n', encoding="utf-8")


def _write_linux_app_root(root: Path, cli_content: bytes) -> None:
    cli = root / "resources" / "management-cli" / "ElfieNestCli"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(cli_content)
    cli.chmod(0o755)
    app_run = root / "AppRun"
    app_run.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    app_run.chmod(0o755)
    manifest = root / "resources" / "manifest.json"
    manifest.write_text('{"version":"0.1.0"}\n', encoding="utf-8")


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
    installed_cli = (
        destination / "Contents" / "Resources" / "management-cli" / "ElfieNestCli"
    )
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


def test_macos_canonical_application_root_is_system_applications_not_home() -> None:
    # Given: a user HOME that must not affect a standard macOS application location.
    environment = {"HOME": "/Users/example", "PATH": "/usr/bin:/bin"}

    # When: the native installer resolves its canonical Darwin destination.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; native_application_root darwin-arm64',
            "native-install",
            str(PROJECT_ROOT / "scripts" / "native_install_artifact.sh"),
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: source install and a dragged DMG target the same standard application root.
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "/Applications/ElfieNest.app"


def test_macos_authorization_adapter_allows_only_the_canonical_system_bundle() -> None:
    script = (PROJECT_ROOT / "scripts" / "native_install_artifact.sh").read_text(
        encoding="utf-8"
    )

    assert "with administrator privileges" in script
    assert "--privileged-macos-install" in script
    assert '"/Applications/ElfieNest.app"' in script
    assert "native-install-macos-authorization-destination-invalid" in script


def test_invalid_upgrade_keeps_the_previous_native_bundle(tmp_path: Path) -> None:
    previous = tmp_path / "Applications" / "ElfieNest.app"
    invalid_source = tmp_path / "ElfieNest.invalid.app"
    _write_macos_bundle(previous, b"previous-cli")
    invalid_source.mkdir()

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; install_macos_app_bundle "$2" "$3"',
            "native-install",
            str(PROJECT_ROOT / "scripts" / "native_install_artifact.sh"),
            str(invalid_source),
            str(previous),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        previous / "Contents" / "Resources" / "management-cli" / "ElfieNestCli"
    ).read_bytes() == b"previous-cli"


def test_native_application_requires_its_packaged_manifest(tmp_path: Path) -> None:
    bundle = tmp_path / "ElfieNest.app"
    _write_macos_bundle(bundle, b"cli")
    (bundle / "Contents" / "Resources" / "manifest.json").unlink()

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; validate_native_application_root darwin-arm64 "$2"',
            "native-install",
            str(PROJECT_ROOT / "scripts" / "native_install_artifact.sh"),
            str(bundle),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


def test_linux_xdg_integration_is_outside_the_application_payload(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    application_root = home / ".local" / "opt" / "ElfieNest"
    _write_linux_app_root(application_root, b"linux-cli")
    (application_root / ".DirIcon").write_text("icon", encoding="utf-8")

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; source "$2"; install_linux_xdg_integration "$3"',
            "native-install",
            str(PROJECT_ROOT / "scripts" / "elfienest_install_helpers.sh"),
            str(PROJECT_ROOT / "scripts" / "native_install_artifact.sh"),
            str(application_root),
        ],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )

    desktop_file = home / ".local" / "share" / "applications" / "elfienest.desktop"
    icon_file = (
        home
        / ".local"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / "elfienest.svg"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Exec={application_root}/AppRun" in desktop_file.read_text(encoding="utf-8")
    assert icon_file.read_text(encoding="utf-8") == "icon"
    assert "/.local/share/" not in str(application_root)


def test_linux_uninstaller_removes_only_verified_xdg_integration(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    application_root = home / ".local" / "opt" / "ElfieNest"
    _write_linux_app_root(application_root, b"linux-cli")
    (application_root / ".DirIcon").write_text("icon", encoding="utf-8")
    wrapper = home / ".local" / "bin" / "elfienest"
    uninstaller = home / ".local" / "bin" / "uninstall-elfienest"
    cli = application_root / "resources" / "management-cli" / "ElfieNestCli"
    desktop_file = home / ".local" / "share" / "applications" / "elfienest.desktop"
    icon_file = (
        home
        / ".local"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / "elfienest.svg"
    )
    helpers = PROJECT_ROOT / "scripts" / "elfienest_install_helpers.sh"
    native_helpers = PROJECT_ROOT / "scripts" / "native_install_artifact.sh"
    environment = {"HOME": str(home), "PATH": "/usr/bin:/bin"}

    prepare = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; source "$2"; '
                'mkdir -p "${3%/*}"; write_managed_wrapper "$3" "$5"; '
                'install_linux_xdg_integration "$4"; '
                'write_managed_uninstaller "$6" "$3" "$6" "$4" "$5" "$7" "$8" "$9"'
            ),
            "native-install",
            str(helpers),
            str(native_helpers),
            str(wrapper),
            str(application_root),
            str(cli),
            str(uninstaller),
            str(desktop_file),
            str(icon_file),
            str(application_root / ".DirIcon"),
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert prepare.returncode == 0, prepare.stdout + prepare.stderr

    result = subprocess.run(
        [str(uninstaller)], env=environment, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not wrapper.exists()
    assert not uninstaller.exists()
    assert not application_root.exists()
    assert not desktop_file.exists()
    assert not icon_file.exists()
