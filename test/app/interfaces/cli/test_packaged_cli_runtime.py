"""Runtime location contracts for the frozen management CLI."""

from __future__ import annotations

from pathlib import Path

from app.interfaces.cli import packaged_runtime


def test_frozen_cli_discovers_its_sibling_core_without_a_checkout(
    tmp_path: Path,
) -> None:
    # Given: the CLI's standard resource location inside an installed app bundle.
    resources = tmp_path / "ElfieNest.app" / "Contents" / "Resources"
    cli = resources / "management-cli" / "ElfieNestCli"
    core = resources / "python-core" / "ElfieNestCore"
    cli.parent.mkdir(parents=True)
    core.parent.mkdir(parents=True)
    cli.write_bytes(b"cli")
    core.write_bytes(b"core")
    environment: dict[str, str] = {}

    # When: a frozen CLI configures its runtime environment.
    packaged_runtime.configure_frozen_cli_runtime(
        executable=cli,
        platform="darwin",
        environment=environment,
    )

    # Then: every installed-runtime consumer resolves only packaged resources.
    assert environment == {
        "ELFIENEST_CORE_BIN": str(core),
        "ELFIENEST_WEB_BUILD_DIR": str(resources / "web"),
        "ELFIENEST_GODOT_WEB_DIR": str(resources / "godot-web"),
        "ELFIENEST_BUNDLED_CONFIG_DIR": str(resources / "config"),
        "ELFIENEST_RUNTIME_MODE": "release",
        "ELFIENEST_PROJECT_ROOT": str(resources.parent.parent),
        "ELFIENEST_DESKTOP_BIN": str(resources.parent / "MacOS" / "ElfieNest"),
        "PYINSTALLER_RESET_ENVIRONMENT": "1",
    }


def test_frozen_cli_reads_the_packaged_manifest_version_without_distribution_metadata(
    tmp_path: Path,
) -> None:
    # Given: a standalone application bundle whose frozen CLI has no wheel metadata.
    resources = tmp_path / "ElfieNest.app" / "Contents" / "Resources"
    cli = resources / "management-cli" / "ElfieNestCli"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"cli")
    (resources / "manifest.json").write_text(
        '{"application_version":"0.1.0"}\n', encoding="utf-8"
    )

    # When: the installed CLI resolves its application version from its sibling resources.
    version = packaged_runtime.packaged_application_version(cli)

    # Then: it reports the release version without needing a source checkout or wheel.
    assert version == "0.1.0"
