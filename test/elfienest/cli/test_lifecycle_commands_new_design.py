from __future__ import annotations

from argparse import Namespace

import pytest

from elfienest.cli import lifecycle_commands
from elfienest.operations.service import PortStatus
from elfienest.operations.service_lifecycle_types import ServiceLifecycleResult
from scripts import elfienest


def test_start_is_idempotent_when_service_is_already_running(monkeypatch, capsys) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: calls.append("start")
        or ServiceLifecycleResult(status="already_running", pid=42),
    )

    # When
    lifecycle_commands.start_background_service()

    # Then
    assert calls == ["start"]
    assert "已在运行" in capsys.readouterr().out


def test_start_rejects_fixed_port_collision_before_launch(
    monkeypatch, capsys
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: calls.append("start")
        or ServiceLifecycleResult(status="started", pid=1),
    )

    result = lifecycle_commands.start_background_service(
        ("python", "scripts/serve.py", "--port", "8767")
    )

    assert result.status == "failed"
    assert calls == []
    assert "端口" in capsys.readouterr().out


def test_start_forwards_custom_internal_ports(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: commands.append(tuple(kwargs["command"]))
        or ServiceLifecycleResult(status="started", pid=44),
    )

    # When
    lifecycle_commands.start_background_service(
        lifecycle_commands.default_service_command(
            (
                "--port",
                "8100",
                "--ws-port",
                "8866",
                "--godot-ws-port",
                "8768",
                "--audio-port",
                "8769",
            )
        )
    )

    # Then
    assert commands[0][-8:] == (
        "--port",
        "8100",
        "--ws-port",
        "8866",
        "--godot-ws-port",
        "8768",
        "--audio-port",
        "8769",
    )


def test_restart_does_not_pass_force_flag(monkeypatch, capsys) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "stop_service",
        lambda *args, **kwargs: ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py", "--fallback")
        ),
    )

    def fake_start(*args, **kwargs):
        commands.append(tuple(kwargs["command"]))
        return ServiceLifecycleResult(status="started", pid=43)

    monkeypatch.setattr(lifecycle_commands, "start_service", fake_start)

    # When
    lifecycle_commands.restart_background_service()

    # Then
    assert commands == [("python", "scripts/serve.py", "--fallback")]
    assert "--force" not in commands[0]
    assert "已重启" in capsys.readouterr().out


def test_dispatch_propagates_lifecycle_failure(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        elfienest,
        "stop_background_service",
        lambda: ServiceLifecycleResult(status="failed"),
    )

    # When / Then
    with pytest.raises(SystemExit) as error:
        elfienest.dispatch_command(Namespace(command="stop"))
    assert error.value.code == 1


def test_web_opens_the_tracked_service_port(monkeypatch) -> None:
    # Given
    opened: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "existing_service_command",
        lambda *args: (42, ("python", "scripts/serve.py", "--port", "8100")),
    )
    monkeypatch.setattr(lifecycle_commands, "_web_is_healthy", lambda port=8000: port == 8100)
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    # When
    result = lifecycle_commands.open_web_console()

    # Then
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8100/"]


def test_status_reports_the_tracked_service_ports(monkeypatch, capsys) -> None:
    # Given
    checked: list[tuple[int, str]] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "existing_service_command",
        lambda *args: (
            42,
            (
                "python",
                "scripts/serve.py",
                "--port",
                "8100",
                "--ws-port",
                "8866",
                "--godot-ws-port",
                "8768",
                "--audio-port",
                "8769",
            ),
        ),
    )

    def fake_check_port(port: int, name: str):
        checked.append((port, name))
        return PortStatus(port, name, True)

    monkeypatch.setattr("elfienest.operations.service.check_port", fake_check_port)

    # When
    lifecycle_commands.show_service_status()

    # Then
    output = capsys.readouterr().out
    assert (8100, "HTTP 服务") in checked
    assert (8866, "WebSocket (管理)") in checked
    assert (8768, "WebSocket (Godot)") in checked
    assert (8769, "音频服务器") in checked
    assert "端口 8100" in output
    assert "端口 8866" in output
