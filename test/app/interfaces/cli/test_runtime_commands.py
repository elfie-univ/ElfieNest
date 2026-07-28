from __future__ import annotations

from importlib import metadata
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from app.interfaces.cli import runtime_commands


def test_show_version_prints_current_version(capsys: CaptureFixture[str]) -> None:
    runtime_commands.show_version()

    output = capsys.readouterr().out
    assert f"ElfieNest v{metadata.version('elfienest')}" in output


def test_version_uses_the_packaged_manifest_when_frozen_metadata_is_absent(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    # Given: a frozen CLI with a release manifest but without installed wheel metadata.
    resources = tmp_path / "ElfieNest.app" / "Contents" / "Resources"
    cli = resources / "management-cli" / "ElfieNestCli"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"cli")
    (resources / "manifest.json").write_text(
        '{"application_version":"0.1.0"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        runtime_commands.metadata,
        "version",
        lambda _package: (_ for _ in ()).throw(metadata.PackageNotFoundError),
    )
    monkeypatch.setattr(runtime_commands.sys, "executable", str(cli))

    # When: the CLI reads its version outside a source checkout.
    version = runtime_commands._current_version()

    # Then: it reports the packaged release version rather than `unknown`.
    assert version == "0.1.0"


def test_show_status_reports_database_unavailable(
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runtime_commands, "default_port_statuses", lambda: [])
    monkeypatch.setattr(
        runtime_commands,
        "collect_usage_stats",
        lambda: (_ for _ in ()).throw(runtime_commands.DatabaseUnavailableError()),
    )

    runtime_commands.show_status()

    output = capsys.readouterr().out
    assert "Database not initialized" in output


def test_runtime_commands_does_not_expose_legacy_process_killers() -> None:
    assert not hasattr(runtime_commands, "restart_service")
    assert not hasattr(runtime_commands, "stop_service")
    assert not hasattr(runtime_commands, "_start_web_service_process")
