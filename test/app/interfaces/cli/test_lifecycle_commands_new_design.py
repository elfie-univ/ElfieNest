from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.features.administration.system_service import PortStatus
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle.types import ServiceLifecycleResult
from scripts import elfienest


@pytest.fixture(autouse=True)
def isolate_lifecycle_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        lifecycle_commands, "get_elfie_home", lambda: tmp_path / "elfie-home"
    )


def test_lifecycle_commands_use_repository_root_for_service_command() -> None:
    # Given
    repo_root = Path(__file__).resolve().parents[4]

    # When
    command = lifecycle_commands.default_service_command()

    # Then
    assert lifecycle_commands.PROJECT_ROOT == repo_root
    assert command[1] == str(repo_root / "scripts" / "serve.py")


def test_start_is_idempotent_when_service_is_already_running(
    monkeypatch, capsys
) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: (
            calls.append("start")
            or ServiceLifecycleResult(status="already_running", pid=42)
        ),
    )

    # When
    lifecycle_commands.start_background_service()

    # Then
    assert calls == ["start"]
    assert "already running" in capsys.readouterr().out


def test_start_rejects_godot_port_collision_before_launch(monkeypatch, capsys) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: (
            calls.append("start") or ServiceLifecycleResult(status="started", pid=1)
        ),
    )

    result = lifecycle_commands.start_background_service(
        ("python", "scripts/serve.py", "--port", "8765")
    )

    assert result.status == "failed"
    assert calls == []
    assert "port" in capsys.readouterr().out


def test_start_forwards_custom_service_ports(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: (
            commands.append(tuple(kwargs["command"]))
            or ServiceLifecycleResult(status="started", pid=44)
        ),
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
            )
        )
    )

    # Then
    assert commands[0][-6:] == (
        "--port",
        "8100",
        "--ws-port",
        "8866",
        "--godot-ws-port",
        "8768",
    )


def test_start_uses_core_when_desktop_executable_is_present(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    timeouts: list[float] = []
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "find_desktop_executable",
        lambda *args: Path("/tmp/ElfieNestDesktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "start_desktop_application",
        lambda *args, **kwargs: pytest.fail("start must not launch Desktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: (
            commands.append(tuple(kwargs["command"]))
            or timeouts.append(kwargs["timeout_seconds"])
            or ServiceLifecycleResult(status="started", pid=44)
        ),
    )

    # When
    result = lifecycle_commands.start_background_service()

    # Then
    assert result.status == "started"
    assert commands == [lifecycle_commands.default_service_command(("--lan",))]
    assert timeouts == [lifecycle_commands.BACKGROUND_START_TIMEOUT_SECONDS]


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
    assert "restarted" in capsys.readouterr().out


def test_restart_uses_core_when_desktop_executable_is_present(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    timeouts: list[float] = []
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "find_desktop_executable",
        lambda *args: Path("/tmp/ElfieNestDesktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "stop_desktop_application",
        lambda *args: pytest.fail("restart must not stop Desktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "start_desktop_application",
        lambda *args, **kwargs: pytest.fail("restart must not launch Desktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "stop_service",
        lambda *args: ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py", "--fallback")
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "start_service",
        lambda *args, **kwargs: (
            commands.append(tuple(kwargs["command"]))
            or timeouts.append(kwargs["timeout_seconds"])
            or ServiceLifecycleResult(status="started", pid=43)
        ),
    )

    # When
    result = lifecycle_commands.restart_background_service()

    # Then
    assert result.status == "started"
    assert commands == [("python", "scripts/serve.py", "--fallback")]
    assert timeouts == [lifecycle_commands.BACKGROUND_START_TIMEOUT_SECONDS]


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
    monkeypatch.setattr(
        lifecycle_commands, "_web_is_healthy", lambda port=8000: port == 8100
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    # When
    result = lifecycle_commands.open_web_console()

    # Then
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8100/"]


def test_web_uses_core_when_desktop_executable_is_present(monkeypatch) -> None:
    # Given
    opened: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "find_desktop_executable",
        lambda *args: Path("/tmp/ElfieNestDesktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "start_desktop_application",
        lambda *args, **kwargs: pytest.fail("web must not launch Desktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands, "existing_service_command", lambda *args: None
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda: ServiceLifecycleResult(
            status="started",
            command=("python", "scripts/serve.py", "--port", "8100"),
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands, "_web_is_healthy", lambda port=8000: port == 8100
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    # When
    result = lifecycle_commands.open_web_console()

    # Then
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8100/"]


def test_stop_uses_core_when_desktop_pid_is_present(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "stop_desktop_application",
        lambda *args: pytest.fail("stop must not stop Desktop"),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "stop_service",
        lambda *args: ServiceLifecycleResult(status="stopped", pid=44),
    )

    # When
    result = lifecycle_commands.stop_background_service()

    # Then
    assert result.status == "stopped"


def test_status_does_not_report_desktop_lifecycle(monkeypatch, capsys) -> None:
    # Given
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "desktop_process_id",
        lambda *args: pytest.fail("status must inspect Core only"),
    )
    monkeypatch.setattr(
        lifecycle_commands, "existing_service_command", lambda *args: None
    )

    # When
    lifecycle_commands.show_service_status()

    # Then
    assert "Service Status" in capsys.readouterr().out


def test_explicit_desktop_command_starts_desktop(monkeypatch) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands.desktop_lifecycle,
        "start_desktop_application",
        lambda *args, **kwargs: (
            calls.append("desktop") or ServiceLifecycleResult(status="started", pid=44)
        ),
    )

    # When
    result = lifecycle_commands.start_desktop_application()

    # Then
    assert result.status == "started"
    assert calls == ["desktop"]


def test_product_start_options_enable_lan_by_default_and_allow_loopback() -> None:
    # Given
    default_start = Namespace(
        port=None,
        ws_port=None,
        godot_ws_port=None,
        fallback=False,
        no_seed_elfie=False,
        lan=True,
    )
    loopback_start = Namespace(
        port=None,
        ws_port=None,
        godot_ws_port=None,
        fallback=False,
        no_seed_elfie=False,
        lan=False,
    )

    # When
    default_options = elfienest._service_options_from_args(default_start)
    loopback_options = elfienest._service_options_from_args(loopback_start)

    # Then
    assert default_options == ("--lan",)
    assert loopback_options == ()


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
            ),
        ),
    )

    def fake_check_port(port: int, name: str):
        checked.append((port, name))
        return PortStatus(port, name, True)

    monkeypatch.setattr(
        "app.features.administration.system_service.check_port", fake_check_port
    )

    # When
    lifecycle_commands.show_service_status()

    # Then
    output = capsys.readouterr().out
    assert (8100, "HTTP") in checked
    assert (8866, "WebSocket (admin)") in checked
    assert (8768, "WebSocket (Godot)") in checked
    assert "port 8100" in output
    assert "port 8866" in output
