from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.bootstrap.lifecycle import create_lifecycle_facade
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle import ServicePortStatus
from app.orchestration.lifecycle.runtime_health import (
    OwnerLease,
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.types import ServiceLifecycleResult
from scripts import elfienest

LIFECYCLE = create_lifecycle_facade()


@pytest.fixture(autouse=True)
def isolate_lifecycle_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        lifecycle_commands, "get_elfie_home", lambda: tmp_path / "elfie-home"
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_lifecycle_receipt_home",
        lambda: tmp_path / "lifecycle-home",
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda: None,
        raising=False,
    )


class _LaunchSupervisor:
    def __init__(
        self,
        health: RuntimeHealth,
        events: list[str],
        *,
        start_result: ServiceLifecycleResult | None = None,
        stop_result: ServiceLifecycleResult | None = None,
    ) -> None:
        self.health = health
        self.events = events
        self.start_result = start_result or ServiceLifecycleResult(
            status="started", pid=42
        )
        self.stop_result = stop_result or ServiceLifecycleResult(status="stopped")

    def status(self) -> RuntimeHealth:
        self.events.append("status")
        return self.health

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        assert owner_id == "cli"
        self.events.append("start")
        return self.start_result

    def stop(self) -> ServiceLifecycleResult:
        self.events.append("stop")
        return self.stop_result


def _stable_health() -> RuntimeHealth:
    return RuntimeHealth(
        state=RuntimeHealthState.READY,
        generation=1,
        owner_lease=OwnerLease(owner_id="cli", generation=1),
        components=(),
    )


def _stopped_health() -> RuntimeHealth:
    return RuntimeHealth(
        state=RuntimeHealthState.STOPPED,
        generation=0,
        owner_lease=None,
        components=(),
    )


def test_start_when_stably_running_skips_frontend_preflight(monkeypatch) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(
        _stable_health(),
        events,
        start_result=ServiceLifecycleResult(status="already_running", pid=42),
    )
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda: events.append("build"),
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
    )

    assert result.status == "already_running"
    assert events == ["status", "start"]


def test_start_when_stopped_prepares_frontend_before_launch(monkeypatch) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(_stopped_health(), events)
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda: events.append("build"),
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
    )

    assert result.status == "started"
    assert events == ["status", "build", "start"]


def test_start_does_not_launch_when_frontend_preflight_fails(monkeypatch) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(_stopped_health(), events)
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )

    def fail() -> None:
        events.append("build")
        from app.interfaces.web.frontend_build import FrontendBuildError

        raise FrontendBuildError("frontend is stale")

    monkeypatch.setattr(lifecycle_commands, "_prepare_frontend_for_launch", fail)

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
    )

    assert result.status == "failed"
    assert events == ["status", "build"]
    assert result.error is not None


def test_restart_prepares_frontend_before_stopping_old_service(monkeypatch) -> None:
    events: list[str] = []
    stopped = _LaunchSupervisor(
        _stable_health(),
        events,
        stop_result=ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py")
        ),
    )
    started = _LaunchSupervisor(_stopped_health(), events)
    supervisors = iter((stopped, started))
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: next(supervisors),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda: events.append("build"),
    )

    result = lifecycle_commands.restart_background_service(LIFECYCLE)

    assert result.status == "started"
    assert events == ["build", "stop", "start"]


def test_restart_build_failure_keeps_old_service_running(monkeypatch) -> None:
    events: list[str] = []
    stopped = _LaunchSupervisor(_stable_health(), events)
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: stopped
    )

    def fail() -> None:
        events.append("build")
        from app.interfaces.web.frontend_build import FrontendBuildError

        raise FrontendBuildError("frontend build failed")

    monkeypatch.setattr(lifecycle_commands, "_prepare_frontend_for_launch", fail)

    result = lifecycle_commands.restart_background_service(LIFECYCLE)

    assert result.status == "failed"
    assert events == ["build"]


def test_stop_never_runs_frontend_preflight(monkeypatch) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(_stable_health(), events)
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda: pytest.fail("stop must not build frontend"),
    )

    result = lifecycle_commands.stop_background_service(
        LIFECYCLE,
    )

    assert result.status == "stopped"
    assert events == ["stop"]


def test_release_lifecycle_preflight_is_a_no_op(monkeypatch) -> None:
    monkeypatch.setenv("ELFIENEST_RUNTIME_MODE", "release")
    monkeypatch.setattr(
        lifecycle_commands,
        "ensure_frontend_build",
        lambda **_kwargs: pytest.fail("release lifecycle must not build frontend"),
    )

    lifecycle_commands._prepare_frontend_for_launch()


def test_lifecycle_commands_use_repository_root_for_service_command() -> None:
    # Given
    repo_root = Path(__file__).resolve().parents[4]

    # When
    command = lifecycle_commands.default_service_command()

    # Then
    assert lifecycle_commands.PROJECT_ROOT == repo_root
    assert command[1] == str(repo_root / "scripts" / "serve.py")


def test_authority_start_budget_covers_cold_godot_web_boot() -> None:
    # Given: a real cold Godot Web authority remained unready after 30 seconds.
    # When / Then: the product budget preserves the observed successful 120-second window.
    assert lifecycle_commands.AUTHORITY_START_TIMEOUT_SECONDS == 120.0


def test_start_is_idempotent_when_service_is_already_running(
    monkeypatch, capsys
) -> None:
    # Given
    events: list[str] = []
    supervisor = _LaunchSupervisor(
        _stable_health(),
        events,
        start_result=ServiceLifecycleResult(status="already_running", pid=42),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: supervisor,
    )

    # When
    lifecycle_commands.start_background_service(LIFECYCLE)

    # Then
    assert events == ["status", "start"]
    assert "already running" in capsys.readouterr().out


def test_start_rejects_godot_port_collision_before_launch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: pytest.fail("invalid ports must not build Runtime"),
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE, ("python", "scripts/serve.py", "--port", "8765")
    )

    assert result.status == "failed"
    assert "port" in capsys.readouterr().out


def test_start_forwards_custom_service_ports(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    supervisor = _LaunchSupervisor(_stopped_health(), [])

    def build_supervisor(_lifecycle, command, _port, **_kwargs):
        commands.append(tuple(command))
        return supervisor

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)

    # When
    lifecycle_commands.start_background_service(
        LIFECYCLE,
        lifecycle_commands.default_service_command(
            (
                "--port",
                "8100",
                "--ws-port",
                "8866",
                "--godot-ws-port",
                "8768",
            )
        ),
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
    supervisor = _LaunchSupervisor(_stopped_health(), [])
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *_args, **_kwargs: pytest.fail("start must not launch Desktop"),
    )

    def build_supervisor(_lifecycle, command, _port, **_kwargs):
        commands.append(tuple(command))
        return supervisor

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)

    # When
    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
    )

    # Then
    assert result.status == "started"
    assert commands == [lifecycle_commands.default_service_command(("--lan",))]


def test_restart_does_not_pass_force_flag(monkeypatch, capsys) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    stopped = _LaunchSupervisor(
        _stable_health(),
        [],
        stop_result=ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py", "--fallback")
        ),
    )
    started = _LaunchSupervisor(_stopped_health(), [])
    calls = 0

    def build_supervisor(_lifecycle, command, _port, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return stopped
        commands.append(tuple(command))
        return started

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)

    # When
    lifecycle_commands.restart_background_service(LIFECYCLE)

    # Then
    assert commands == [("python", "scripts/serve.py", "--fallback")]
    assert "--force" not in commands[0]
    assert "restarted" in capsys.readouterr().out


def test_restart_emits_one_final_success_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda: None,
    )
    stopped = _LaunchSupervisor(
        _stable_health(),
        [],
        stop_result=ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py")
        ),
    )
    started = _LaunchSupervisor(_stopped_health(), [])
    supervisors = iter((stopped, started))
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: next(supervisors),
    )

    lifecycle_commands.restart_background_service(LIFECYCLE)

    output = capsys.readouterr().out
    assert "\r  ✅ Restarting service ✓" not in output
    assert output.count("Service restarted") == 1


def test_restart_uses_core_when_desktop_executable_is_present(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *_args, **_kwargs: pytest.fail("restart must not launch Desktop"),
    )
    stopped = _LaunchSupervisor(
        _stable_health(),
        [],
        stop_result=ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py", "--fallback")
        ),
    )
    started = _LaunchSupervisor(_stopped_health(), [])
    calls = 0

    def build_supervisor(_lifecycle, command, _port, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return stopped
        commands.append(tuple(command))
        return started

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)

    # When
    result = lifecycle_commands.restart_background_service(LIFECYCLE)

    # Then
    assert result.status == "started"
    assert commands == [("python", "scripts/serve.py", "--fallback")]


def test_dispatch_propagates_lifecycle_failure(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        elfienest,
        "stop_background_service",
        lambda _lifecycle: ServiceLifecycleResult(status="failed"),
    )

    # When / Then
    with pytest.raises(SystemExit) as error:
        elfienest.dispatch_command(Namespace(command="stop"))
    assert error.value.code == 1


def test_web_opens_the_tracked_service_port(monkeypatch) -> None:
    # Given
    opened: list[str] = []
    monkeypatch.setattr(
        LIFECYCLE,
        "existing_service_command",
        lambda *args: (42, ("python", "scripts/serve.py", "--port", "8100")),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: port == 8100,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    # When
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8100/"]


def test_web_uses_core_when_desktop_executable_is_present(monkeypatch) -> None:
    # Given
    opened: list[str] = []
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *_args, **_kwargs: pytest.fail("web must not launch Desktop"),
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda _lifecycle: ServiceLifecycleResult(
            status="started",
            command=("python", "scripts/serve.py", "--port", "8100"),
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000: port == 8100,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    # When
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8100/"]


def test_stop_uses_core_when_desktop_pid_is_present(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        LIFECYCLE,
        "stop_desktop",
        lambda *_args: pytest.fail("stop must not stop Desktop"),
    )
    supervisor = _LaunchSupervisor(
        _stable_health(),
        [],
        stop_result=ServiceLifecycleResult(status="stopped", pid=44),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: supervisor,
    )

    # When
    result = lifecycle_commands.stop_background_service(LIFECYCLE)

    # Then
    assert result.status == "stopped"


def test_status_does_not_report_desktop_lifecycle(monkeypatch, capsys) -> None:
    # Given
    monkeypatch.setattr(
        LIFECYCLE,
        "desktop_process_id",
        lambda *_args: pytest.fail("status must inspect Core only"),
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(LIFECYCLE, "default_port_statuses", lambda: ())
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: _LaunchSupervisor(_stopped_health(), []),
    )

    # When
    lifecycle_commands.show_service_status(LIFECYCLE)

    # Then
    assert "Service Status" in capsys.readouterr().out


def test_explicit_desktop_command_starts_desktop(monkeypatch) -> None:
    # Given
    calls: list[str] = []
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *args, **kwargs: (
            calls.append("desktop") or ServiceLifecycleResult(status="started", pid=44)
        ),
    )

    # When
    result = lifecycle_commands.start_desktop_application(LIFECYCLE)

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
        LIFECYCLE,
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

    def fake_statuses(http_port: int, websocket_port: int, godot_ws_port: int):
        checked.extend(
            (
                (http_port, "HTTP"),
                (websocket_port, "WebSocket (admin)"),
                (godot_ws_port, "WebSocket (Godot)"),
            )
        )
        return tuple(
            ServicePortStatus(port=port, name=name, running=True)
            for port, name in checked
        )

    monkeypatch.setattr(LIFECYCLE, "service_port_statuses", fake_statuses)
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: _LaunchSupervisor(_stopped_health(), []),
    )

    # When
    lifecycle_commands.show_service_status(LIFECYCLE)

    # Then
    output = capsys.readouterr().out
    assert (8100, "HTTP") in checked
    assert (8866, "WebSocket (admin)") in checked
    assert (8768, "WebSocket (Godot)") in checked
    assert "port 8100" in output
    assert "port 8866" in output
