"""Runtime location contracts for the frozen management CLI."""

from __future__ import annotations

from pathlib import Path

from app.interfaces.cli import packaged_runtime


def test_frozen_cli_discovers_its_sibling_core_without_a_checkout(tmp_path: Path) -> None:
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

    # Then: lifecycle operations receive only the sibling Core executable path.
    assert environment == {"ELFIENEST_CORE_BIN": str(core)}
