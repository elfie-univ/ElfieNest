from __future__ import annotations

from _pytest.capture import CaptureFixture

from elfienest.cli import runtime_commands


def test_show_version_prints_current_version(capsys: CaptureFixture[str]) -> None:
    runtime_commands.show_version()

    output = capsys.readouterr().out
    assert "ElfieNest v1.0.0" in output


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
