from __future__ import annotations

from _pytest.capture import CaptureFixture

from app.interfaces.cli import runtime_commands


def test_show_version_prints_current_version(capsys: CaptureFixture[str]) -> None:
    runtime_commands.show_version()

    output = capsys.readouterr().out
    assert "ElfieNest v0.1.0" in output


def test_show_version_prints_project_release_version(
    capsys: CaptureFixture[str],
) -> None:
    # Given: the configured application release version.

    # When: the version command renders its user-facing output.
    runtime_commands.show_version()

    # Then: it renders the configured release version.
    assert "ElfieNest v0.1.0" in capsys.readouterr().out


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
    assert "数据库未初始化" in output


def test_runtime_commands_does_not_expose_legacy_process_killers() -> None:
    assert not hasattr(runtime_commands, "restart_service")
    assert not hasattr(runtime_commands, "stop_service")
    assert not hasattr(runtime_commands, "_start_web_service_process")
