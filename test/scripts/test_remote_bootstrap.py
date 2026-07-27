"""Contracts for the source-free remote native-package bootstrap."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from test.support.paths import PROJECT_ROOT


def test_remote_bootstrap_dry_run_reads_only_the_current_target_manifest(
    tmp_path: Path,
) -> None:
    """Dry-run prints the selected native package without downloading or installing it."""
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.1.0",
                "artifacts": [
                    {
                        "target": "darwin-x64",
                        "url": "http://127.0.0.1:8999/ElfieNest.dmg",
                        "size": 123,
                        "sha256": "a" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "remote_install.sh"),
            "--dry-run",
            "--manifest",
            str(manifest),
        ],
        env={
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin",
            "ELFIENEST_TEST_TARGET": "darwin-x64",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "target=darwin-x64" in result.stdout
    assert "version=0.1.0" in result.stdout
    assert "http://127.0.0.1:8999/ElfieNest.dmg" in result.stdout
    assert not (tmp_path / "home").exists()


def test_published_bootstrap_embeds_the_canonical_native_adapter(
    tmp_path: Path,
) -> None:
    """The curl artifact is built from, rather than a copy of, the native adapter."""
    output = tmp_path / "install.sh"

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "build_remote_bootstrap.sh"),
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    generated = output.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "install_native_artifact()" in generated
    assert "validate_native_application_destination()" in generated
    assert "install_verified_artifact()" in generated
    assert "artifact-checksum-mismatch" in generated


def test_generated_bootstrap_preserves_dry_run_without_a_checkout(
    tmp_path: Path,
) -> None:
    """The generated curl payload is self-contained for a no-download dry-run."""
    output = tmp_path / "install.sh"
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.1.0",
                "artifacts": [
                    {
                        "target": "darwin-x64",
                        "url": "https://example.invalid/ElfieNest.dmg",
                        "size": 123,
                        "sha256": "a" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "build_remote_bootstrap.sh"),
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    result = subprocess.run(
        ["bash", str(output), "--dry-run", "--manifest", str(manifest)],
        env={
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin",
            "ELFIENEST_TEST_TARGET": "darwin-x64",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert build.returncode == 0, build.stdout + build.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert "target=darwin-x64" in result.stdout
    assert not (tmp_path / "home").exists()


def test_windows_bootstrap_has_the_same_verified_native_package_contract() -> None:
    """Windows uses its native installer, but keeps the same manifest/hash boundary."""
    script = (PROJECT_ROOT / "scripts" / "remote_install.ps1").read_text(
        encoding="utf-8"
    )

    assert "win32-x64" in script
    assert "ConvertFrom-Json" in script
    assert "Get-FileHash" in script
    assert "artifact-checksum-mismatch" in script
    assert "Programs\\ElfieNest" in script
    assert "Ollama" not in script


def test_verified_remote_artifact_uses_the_canonical_native_adapter(
    tmp_path: Path,
) -> None:
    """A verified macOS package creates the standalone app and CLI wrapper.

    The fixture replaces only ``hdiutil``: it exposes a valid bundle from a
    temporary directory, so this exercises the real remote bootstrap and
    native-adapter chain without mounting a disk image or writing /Applications.
    """
    bundle = tmp_path / "fixture" / "ElfieNest.app"
    cli = bundle / "Contents" / "Resources" / "management-cli" / "ElfieNestCli"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/bash\nprintf 'elfienest 0.1.0\\n'\n", encoding="utf-8")
    cli.chmod(0o755)
    manifest_resource = bundle / "Contents" / "Resources" / "manifest.json"
    manifest_resource.write_text('{"version":"0.1.0"}\n', encoding="utf-8")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_hdiutil = fake_bin / "hdiutil"
    fake_hdiutil.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        'if [ "$1" = attach ]; then\n'
        '  while [ "$1" != -mountpoint ]; do shift; done\n'
        '  cp -R -- "$FAKE_DMG_BUNDLE" "$2/ElfieNest.app"\n'
        "  exit 0\n"
        "fi\n"
        '[ "$1" = detach ]\n',
        encoding="utf-8",
    )
    fake_hdiutil.chmod(0o755)

    artifact = tmp_path / "ElfieNest.dmg"
    artifact.write_bytes(b"verified-native-package")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.1.0",
                "artifacts": [
                    {
                        "target": "darwin-x64",
                        "url": str(artifact),
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    applications = home / "Applications"
    environment = {
        "HOME": str(home),
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "SHELL": "/bin/bash",
        "FAKE_DMG_BUNDLE": str(bundle),
        "ELFIENEST_TEST_TARGET": "darwin-x64",
        "ELFIENEST_TEST_APPLICATIONS_ROOT": str(applications),
    }

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "remote_install.sh"),
            "--manifest",
            str(manifest),
            "--no-launch",
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    application_root = applications / "ElfieNest.app"
    wrapper = home / ".local" / "bin" / "elfienest"
    assert result.returncode == 0, result.stdout + result.stderr
    wrapper_result = subprocess.run(
        [str(wrapper), "version"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert "remote-bootstrap-installed target=darwin-x64 version=0.1.0" in result.stdout
    assert (application_root / "Contents" / "Resources" / "manifest.json").is_file()
    assert wrapper_result.returncode == 0, wrapper_result.stdout + wrapper_result.stderr
    assert wrapper_result.stdout == "elfienest 0.1.0\n"


def test_tampered_remote_artifact_never_reaches_the_native_adapter(
    tmp_path: Path,
) -> None:
    """Checksum failure preserves the canonical application root and creates no wrapper."""
    artifact = tmp_path / "ElfieNest.dmg"
    artifact.write_bytes(b"tampered")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "0.1.0",
                "artifacts": [
                    {
                        "target": "darwin-x64",
                        "url": str(artifact),
                        "size": len(b"tampered"),
                        "sha256": hashlib.sha256(b"expected").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    applications = tmp_path / "Applications"

    result = subprocess.run(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "remote_install.sh"),
            "--manifest",
            str(manifest),
            "--no-launch",
        ],
        env={
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
            "ELFIENEST_TEST_TARGET": "darwin-x64",
            "ELFIENEST_TEST_APPLICATIONS_ROOT": str(applications),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "artifact-checksum-mismatch" in result.stderr
    assert not (applications / "ElfieNest.app").exists()
    assert not (home / ".local" / "bin" / "elfienest").exists()
