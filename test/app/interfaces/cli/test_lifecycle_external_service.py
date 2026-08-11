from __future__ import annotations

from pathlib import Path

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle import ServicePortStatus
from app.orchestration.lifecycle.ports import ProcessSnapshot

LIFECYCLE = create_lifecycle_facade()
PID_FILENAME = "elfienest.pid"


def test_status_marks_default_ports_as_external_when_pid_belongs_elsewhere(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    # Given: the shared production PID receipt points at another checkout.
    elfie_home = tmp_path / "home"
    elfie_home.mkdir()
    (elfie_home / PID_FILENAME).write_text("15727", encoding="utf-8")
    external_root = tmp_path / "other-checkout"
    external_root.mkdir()
    monkeypatch.setattr(
        LIFECYCLE,
        "select_data_home",
        lambda *_args, **_kwargs: elfie_home,
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(LIFECYCLE, "recorded_pid", lambda *_args: 15727)
    monkeypatch.setattr(LIFECYCLE, "process_exists", lambda pid: pid == 15727)
    monkeypatch.setattr(
        LIFECYCLE,
        "inspect_process",
        lambda pid: ProcessSnapshot(
            pid=pid,
            cwd=external_root,
            command=("python", "scripts/serve.py", "--fallback"),
        ),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "default_port_statuses",
        lambda: [ServicePortStatus(port=8000, name="HTTP", running=True)],
    )

    # When: the user asks for status from the current worktree.
    lifecycle_commands.show_service_status(LIFECYCLE)

    # Then: a live external service is not reported as the current project.
    output = capsys.readouterr().out
    assert "another ElfieNest checkout" in output
    assert "occupied by external process" in output
    assert "✅ HTTP" not in output


def test_web_opens_healthy_default_service_without_starting_another_one(
    monkeypatch,
) -> None:
    # Given: no current-project PID receipt is verified, but the default Web is healthy.
    opened: list[str] = []
    start_calls: list[str] = []
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: port == 8000,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda _lifecycle: start_calls.append("start"),
    )

    # When: the user runs `web`.
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then: the existing healthy page opens and no duplicate service is launched.
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8000/"]
    assert start_calls == []


def test_web_reports_external_port_owner_when_default_health_fails(
    monkeypatch,
    capsys,
) -> None:
    # Given: another process occupies the default Web port but is not healthy.
    opened: list[str] = []
    start_calls: list[str] = []
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: False,
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "default_port_statuses",
        lambda: [ServicePortStatus(port=8000, name="HTTP", running=True)],
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda _lifecycle: start_calls.append("start"),
    )

    # When: the user runs `web`.
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then: the CLI reports the external owner class instead of starting again.
    assert result.status == "failed"
    assert opened == []
    assert start_calls == []
    assert "occupied by external process" in capsys.readouterr().out
