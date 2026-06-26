from __future__ import annotations

import subprocess

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


def test_restart_service_reports_failure_when_server_exits(
    monkeypatch,
    tmp_path,
    capsys: CaptureFixture[str],
) -> None:
    class ExitedProcess:
        returncode = 1

        def poll(self) -> int:
            return self.returncode

        def terminate(self) -> None:
            return None

    process = ExitedProcess()

    def fake_popen(*args, **kwargs):
        return process

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0)

    monkeypatch.setattr(runtime_commands, "WEB_LOG_PATH", tmp_path / "web.log", raising=False)
    monkeypatch.setattr(runtime_commands.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(runtime_commands.subprocess, "run", fake_run)
    monkeypatch.setattr(runtime_commands.time, "sleep", lambda _: None)

    runtime_commands.restart_service()

    output = capsys.readouterr().out
    assert "服务启动失败" in output
    assert "服务已重启" not in output
