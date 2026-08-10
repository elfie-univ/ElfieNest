from __future__ import annotations

from importlib import metadata
from pathlib import Path
from unittest.mock import Mock

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from app.features.operations import (
    DatabaseBackupResult,
    OperationsFacade,
    OperationsUnavailable,
    TableCountResult,
    TableCountsResult,
)
from app.interfaces.cli import runtime_commands
from app.orchestration.lifecycle import LifecycleFacade


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
    operations = Mock(spec=OperationsFacade)
    operations.get_usage_stats.side_effect = OperationsUnavailable()
    lifecycle = Mock(spec=LifecycleFacade)
    lifecycle.default_port_statuses.return_value = ()

    runtime_commands.show_status(operations, lifecycle)

    output = capsys.readouterr().out
    assert "Database not initialized" in output


def test_runtime_commands_does_not_expose_legacy_process_killers() -> None:
    assert not hasattr(runtime_commands, "restart_service")
    assert not hasattr(runtime_commands, "stop_service")
    assert not hasattr(runtime_commands, "_start_web_service_process")


def test_database_commands_use_the_injected_operations_facade(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    operations = Mock(spec=OperationsFacade)
    operations.list_table_counts.return_value = TableCountsResult(
        items=(TableCountResult(name="users", count=2),)
    )
    operations.backup_databases.return_value = DatabaseBackupResult(
        backup_path=tmp_path / "backup"
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")

    runtime_commands.dispatch_db(operations, None)
    runtime_commands.dispatch_db(operations, "backup")
    runtime_commands.dispatch_db(operations, "reset")

    output = capsys.readouterr().out
    assert "users: 2 records" in output
    assert str(tmp_path / "backup") in output
    assert "Databases deleted" in output
    operations.list_table_counts.assert_called_once()
    operations.backup_databases.assert_called_once()
    operations.reset_databases.assert_called_once()
