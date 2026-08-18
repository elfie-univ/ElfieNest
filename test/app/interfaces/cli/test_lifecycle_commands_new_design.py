from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bootstrap.system_wiring.lifecycle import create_lifecycle_facade
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle import (
    BackendTier,
    DataHomeInspection,
    DataHomeState,
    EndpointSnapshot,
    LaunchFailedError,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
    ServicePortStatus,
)
from app.orchestration.lifecycle.runtime_snapshot import OwnerLease
from app.orchestration.lifecycle.types import ServiceLifecycleResult
from scripts import elfienest

LIFECYCLE = create_lifecycle_facade()


@pytest.fixture(autouse=True)
def isolate_lifecycle_home(monkeypatch, tmp_path: Path) -> None:
    selected_home = tmp_path / "elfie-home"
    monkeypatch.setattr(
        LIFECYCLE,
        "select_data_home",
        lambda *_args, **_kwargs: selected_home,
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "inspect_data_home",
        lambda *_args, **_kwargs: DataHomeInspection(
            state=DataHomeState.FRESH,
            home=selected_home,
            detail="isolated test data root",
            recoverable=False,
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda *_args: None,
        raising=False,
    )


class _LaunchSupervisor:
    def __init__(
        self,
        health,
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

    def status(self):
        self.events.append("status")
        return self.health

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        assert owner_id == "cli"
        self.events.append("start")
        return self.start_result

    def stop(self) -> ServiceLifecycleResult:
        self.events.append("stop")
        return self.stop_result


def _stable_health():
    return RuntimeSnapshotV1(
        instance_id="test-instance",
        generation=1,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.WORLD_READY,
        desired_target=RuntimeTarget.NORMAL,
        reached_target=RuntimeTarget.WORLD,
        owner_lease=OwnerLease(owner_id="cli", generation=1),
    ).projection()


def _stopped_health():
    return RuntimeSnapshotV1(
        instance_id="test-instance",
        tier=BackendTier.OFFLINE,
        phase=RuntimePhase.OFFLINE,
        desired_target=RuntimeTarget.CORE,
        generation=0,
    ).projection()


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
        lambda *_args: events.append("build"),
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
    )

    assert result.status == "already_running"
    assert events == ["status", "start", "status"]


def test_health_probe_uses_core_published_ports_instead_of_command_defaults() -> None:
    calls: list[str] = []

    class Lifecycle:
        def runtime_snapshot(self, _home: Path) -> RuntimeSnapshotV1:
            return RuntimeSnapshotV1(
                instance_id="instance",
                endpoints=(
                    EndpointSnapshot("http", "http", "127.0.0.1", 12431),
                    EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 12432),
                ),
            )

        def http_get(self, url: str, *, timeout_seconds: float):
            calls.append(url)
            return SimpleNamespace(
                status=200,
                body=b'{"status":"ok","engine_ready":true,"godot_runtime_ready":true}',
            )

        def optional_component_ready(self) -> bool:
            return False

    observation = lifecycle_commands._full_runtime_health(
        Lifecycle(),
        8000,
        8765,
        model_projection=None,
        data_home=Path("/tmp/elfienest"),
    )

    assert calls == ["http://127.0.0.1:12431/api/health"]
    assert [(item.name, item.port) for item in observation.endpoints] == [
        ("http", 12431),
        ("godot_ws", 12432),
    ]


def test_start_when_stopped_prepares_frontend_before_launch(monkeypatch) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(_stopped_health(), events)
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda *_args: events.append("build"),
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
    )

    assert result.status == "started"
    assert events == ["status", "build", "start", "status"]


def test_start_prints_the_published_web_console_url(monkeypatch, capsys) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(
        _stopped_health(),
        events,
        start_result=ServiceLifecycleResult(
            status="started",
            pid=42,
            command=(
                "python",
                "serve.py",
                "--port",
                "15212",
                "--godot-ws-port",
                "15213",
            ),
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )

    result = lifecycle_commands.start_background_service(LIFECYCLE)

    assert result.status == "started"
    assert "Web console: http://127.0.0.1:15212/" in capsys.readouterr().out


def test_packaged_start_uses_background_controller_without_starting_a_second_core(
    monkeypatch,
) -> None:
    # Given: the installed CLI is not being called by the Controller itself.
    calls: list[bool] = []
    timeouts: list[float] = []
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", "/Applications/ElfieNest")
    monkeypatch.delenv("ELFIENEST_CONTROLLER_CLIENT", raising=False)
    monkeypatch.setattr(
        lifecycle_commands, "_should_start_packaged_controller", lambda: True
    )

    def start_desktop(*_args, **kwargs):
        calls.append(kwargs["background"])
        timeouts.append(kwargs["timeout_seconds"])
        return ServiceLifecycleResult(status="started", pid=99)

    monkeypatch.setattr(LIFECYCLE, "start_desktop", start_desktop)

    # When
    result = lifecycle_commands.start_background_service(LIFECYCLE)

    # Then: the packaged command starts the tray Controller in headless mode;
    # Core is started once by the Controller's internal lifecycle client.
    assert result.status == "started"
    assert calls == [True]
    assert timeouts == [lifecycle_commands.BACKGROUND_START_TIMEOUT_SECONDS]


def test_packaged_start_prints_the_published_web_console_url(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", "/Applications/ElfieNest")
    monkeypatch.delenv("ELFIENEST_CONTROLLER_CLIENT", raising=False)
    monkeypatch.setattr(
        lifecycle_commands, "_should_start_packaged_controller", lambda: True
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *_args, **_kwargs: ServiceLifecycleResult(status="started", pid=99),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "runtime_snapshot",
        lambda *_args, **_kwargs: RuntimeSnapshotV1(
            instance_id="installed-instance",
            endpoints=(
                EndpointSnapshot("http", "http", "127.0.0.1", 15212),
                EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 15213),
            ),
        ),
    )

    result = lifecycle_commands.start_background_service(LIFECYCLE)

    assert result.status == "started"
    assert "Web console: http://127.0.0.1:15212/" in capsys.readouterr().out


def test_web_command_does_not_show_mobile_access(monkeypatch) -> None:
    monkeypatch.setattr(
        elfienest,
        "open_web_console",
        lambda _lifecycle, **_kwargs: ServiceLifecycleResult(
            status="already_running", command=("--port", "15212")
        ),
    )
    monkeypatch.setattr(
        elfienest,
        "show_mobile_access",
        lambda *_args, **_kwargs: pytest.fail("web must not show mobile access"),
    )
    monkeypatch.setattr(elfienest, "_exit_on_lifecycle_failure", lambda _result: None)

    elfienest._dispatch_command(Namespace(command="web"), LIFECYCLE)


def test_web_after_packaged_start_uses_the_published_http_endpoint(
    monkeypatch,
) -> None:
    opened: list[str] = []
    dynamic_runtime = RuntimeSnapshotV1(
        instance_id="packaged-instance",
        generation=4,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", 18234),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 18235),
        ),
    )
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(LIFECYCLE, "default_port_statuses", lambda: ())
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: _LaunchSupervisor(_stopped_health(), []),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "start_background_service",
        lambda _lifecycle: ServiceLifecycleResult(status="started", pid=99),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "runtime_snapshot",
        lambda *_args: dynamic_runtime,
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port, **_kwargs: port == 18234,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    result = lifecycle_commands.open_web_console(LIFECYCLE)

    assert result.status == "already_running"
    assert result.command == ("--port", "18234")
    assert opened == ["http://127.0.0.1:18234/"]


def test_mobile_command_uses_the_published_http_endpoint(monkeypatch) -> None:
    accesses: list[tuple[int | None, bool]] = []
    monkeypatch.setattr(
        elfienest,
        "selected_runtime_data_home",
        lambda _lifecycle: Path("/tmp/selected-elfienest"),
    )
    monkeypatch.setattr(
        elfienest,
        "published_http_port_for_home",
        lambda _lifecycle, _home: 18234,
    )
    monkeypatch.setattr(elfienest, "build_operations_facade", lambda _path: object())
    monkeypatch.setattr(elfienest, "get_db_path", lambda: "/tmp/nest.db")
    monkeypatch.setattr(
        elfienest,
        "show_mobile_access",
        lambda _lifecycle, _operations, *, http_port, clear_terminal, **_kwargs: (
            accesses.append((http_port, clear_terminal)) or 0
        ),
    )

    with pytest.raises(SystemExit) as exit_signal:
        elfienest._dispatch_command(Namespace(command="mobile"), LIFECYCLE)

    assert exit_signal.value.code == 0
    assert accesses == [(18234, False)]


def test_packaged_start_rejects_data_home_before_controller_or_desktop_launch(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", "/Applications/ElfieNest")
    monkeypatch.delenv("ELFIENEST_CONTROLLER_CLIENT", raising=False)
    monkeypatch.setattr(
        lifecycle_commands, "_should_start_packaged_controller", lambda: True
    )
    calls: list[str] = []
    monkeypatch.setattr(
        LIFECYCLE,
        "controller_request",
        lambda *_args, **_kwargs: (
            calls.append("controller")
            or pytest.fail("invalid packaged data-home must fail before IPC")
        ),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *_args, **_kwargs: pytest.fail(
            "invalid packaged data-home must not launch Desktop"
        ),
    )

    result = lifecycle_commands.start_background_service(
        LIFECYCLE,
        ("python", "scripts/serve.py", "--data-home", "/tmp/other"),
    )

    assert result.status == "failed"
    assert result.error is not None
    assert "does not support --data-home" in str(result.error)
    assert calls == []
    assert "does not support --data-home" in capsys.readouterr().out


def test_packaged_start_surfaces_controller_failure(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", "/Applications/ElfieNest")
    monkeypatch.delenv("ELFIENEST_CONTROLLER_CLIENT", raising=False)
    monkeypatch.setattr(
        lifecycle_commands, "_should_start_packaged_controller", lambda: True
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "controller_request",
        lambda *_args, **_kwargs: {
            "state": "failed",
            "reason": "Core could not bind its endpoint",
        },
    )

    result = lifecycle_commands.start_background_service(LIFECYCLE)

    assert result.status == "failed"
    assert result.error is not None
    assert "Core could not bind its endpoint" in str(result.error)
    assert "Core could not bind its endpoint" in capsys.readouterr().out


def test_packaged_stop_waits_for_confirmed_offline_state(monkeypatch) -> None:
    monkeypatch.setenv("ELFIENEST_DESKTOP_BIN", "/Applications/ElfieNest")
    monkeypatch.delenv("ELFIENEST_CONTROLLER_CLIENT", raising=False)
    monkeypatch.setattr(
        lifecycle_commands, "_should_start_packaged_controller", lambda: True
    )
    snapshots = iter((_stable_health(), _stopped_health()))
    monkeypatch.setattr(
        LIFECYCLE,
        "controller_request",
        lambda *_args, **_kwargs: {"accepted": True, "state": "stopping"},
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "runtime_snapshot",
        lambda *_args, **_kwargs: next(snapshots),
    )
    stopped_desktop: list[Path] = []
    monkeypatch.setattr(
        LIFECYCLE,
        "stop_desktop",
        lambda home: (
            stopped_desktop.append(home)
            or ServiceLifecycleResult(status="stopped", pid=99)
        ),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "runtime_supervisor",
        lambda *_args, **_kwargs: pytest.fail("Controller stop must own the stop path"),
    )

    result = lifecycle_commands.stop_background_service(LIFECYCLE)

    assert result.status == "stopped"
    assert stopped_desktop


def test_start_reports_incompatible_database_before_launch(monkeypatch, capsys) -> None:
    # Given: the selected root has a schema that belongs to an older ElfieNest version.
    monkeypatch.setattr(
        LIFECYCLE,
        "inspect_data_home",
        lambda *_args, **_kwargs: DataHomeInspection(
            state=DataHomeState.LEGACY,
            home=Path("/tmp/incompatible-elfienest"),
            detail="数据库结构与当前版本不兼容：缺少字段 elfies.home_anchor_id",
            recoverable=True,
        ),
    )
    supervisor = _LaunchSupervisor(_stopped_health(), [])
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )

    # When: the managed start command runs.
    result = lifecycle_commands.start_background_service(LIFECYCLE)

    # Then: the user receives the reason instead of a generic health-check failure.
    assert result.status == "failed"
    assert result.error is not None
    assert "数据库结构与当前版本不兼容" in str(result.error)
    assert "elfies.home_anchor_id" in capsys.readouterr().out


def test_restart_reports_incompatible_database_before_stopping_service(
    monkeypatch, capsys
) -> None:
    # Given: restart would otherwise stop a service before discovering its old schema.
    monkeypatch.setattr(
        LIFECYCLE,
        "inspect_data_home",
        lambda *_args, **_kwargs: DataHomeInspection(
            state=DataHomeState.LEGACY,
            home=Path("/tmp/incompatible-elfienest"),
            detail="数据库结构与当前版本不兼容：缺少字段 elfies.home_anchor_id",
            recoverable=True,
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: pytest.fail(
            "incompatible database must be reported before stopping"
        ),
    )

    # When: the managed restart command runs.
    result = lifecycle_commands.restart_background_service(LIFECYCLE)

    # Then: the old service is left alone and the exact diagnosis is visible.
    assert result.status == "failed"
    assert result.error is not None
    assert "数据库结构与当前版本不兼容" in capsys.readouterr().out


def test_start_does_not_launch_when_frontend_preflight_fails(monkeypatch) -> None:
    events: list[str] = []
    supervisor = _LaunchSupervisor(_stopped_health(), events)
    monkeypatch.setattr(
        lifecycle_commands, "_supervisor_for", lambda *_args, **_kwargs: supervisor
    )

    def fail(*_args) -> None:
        events.append("build")
        from app.orchestration.lifecycle import FrontendPreparationError

        raise FrontendPreparationError("frontend is stale")

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
        lambda *_args: events.append("build"),
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

    def fail(*_args) -> None:
        events.append("build")
        from app.orchestration.lifecycle import FrontendPreparationError

        raise FrontendPreparationError("frontend build failed")

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
        lambda *_args: pytest.fail("stop must not build frontend"),
    )

    result = lifecycle_commands.stop_background_service(
        LIFECYCLE,
    )

    assert result.status == "stopped"
    assert events == ["stop"]


def test_release_lifecycle_preflight_is_a_no_op(monkeypatch) -> None:
    monkeypatch.setenv("ELFIENEST_RUNTIME_MODE", "release")
    monkeypatch.setattr(
        LIFECYCLE,
        "prepare_frontend",
        lambda *_args: pytest.fail("release lifecycle must not build frontend"),
    )

    lifecycle_commands._prepare_frontend_for_launch(LIFECYCLE)


def test_lifecycle_commands_use_repository_root_for_service_command() -> None:
    # Given
    repo_root = Path(__file__).resolve().parents[4]

    # When
    command = LIFECYCLE.default_service_command()

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
    assert events == ["status", "start", "status"]
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
        LIFECYCLE.default_service_command(
            (
                "--port",
                "8100",
                "--godot-ws-port",
                "8768",
            )
        ),
    )

    # Then
    assert commands[0][-4:] == (
        "--port",
        "8100",
        "--godot-ws-port",
        "8768",
    )


def test_start_moves_implicit_default_ports_when_external_process_occupies_them(
    monkeypatch,
) -> None:
    commands: list[tuple[str, ...]] = []
    supervisor = _LaunchSupervisor(_stopped_health(), [])

    def build_supervisor(_lifecycle, command, _port, **_kwargs):
        commands.append(tuple(command))
        return supervisor

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)
    monkeypatch.setattr(
        LIFECYCLE,
        "ports_in_use",
        lambda ports: tuple(ports) == (8000, 8765),
    )

    result = lifecycle_commands.start_background_service(LIFECYCLE)

    assert result.status == "started"
    assert commands[0] == LIFECYCLE.default_service_command(("--lan",))
    assert "--port" in commands[-1]
    assert "--godot-ws-port" in commands[-1]
    assert commands[-1] != commands[0]


def test_start_retries_an_implicit_bind_conflict_on_a_new_pair(monkeypatch) -> None:
    commands: list[tuple[str, ...]] = []
    supervisors = [
        _LaunchSupervisor(
            _stopped_health(),
            [],
            start_result=ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError("[Errno 48] Address already in use"),
            ),
        ),
        _LaunchSupervisor(_stopped_health(), []),
    ]

    def build_supervisor(_lifecycle, command, _port, **_kwargs):
        commands.append(tuple(command))
        return supervisors.pop(0)

    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)
    monkeypatch.setattr(LIFECYCLE, "ports_in_use", lambda _ports: False)

    result = lifecycle_commands.start_background_service(LIFECYCLE)

    assert result.status == "started"
    assert len(commands) == 2
    assert "--port" not in commands[0]
    assert "--port" in commands[1]
    assert "--godot-ws-port" in commands[1]


def test_start_uses_core_when_desktop_executable_is_present(monkeypatch) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    supervisor = _LaunchSupervisor(_stopped_health(), [])
    monkeypatch.setattr(
        LIFECYCLE,
        "start_desktop",
        lambda *_args, **_kwargs: pytest.fail("start must not launch Desktop"),
    )
    monkeypatch.setattr(LIFECYCLE, "ports_in_use", lambda _ports: False)

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
    assert commands == [LIFECYCLE.default_service_command(("--lan",))]


def test_restart_does_not_pass_force_flag(monkeypatch, capsys) -> None:
    # Given
    commands: list[tuple[str, ...]] = []
    stopped = _LaunchSupervisor(
        _stable_health(),
        [],
        stop_result=ServiceLifecycleResult(
            status="stopped", command=("python", "scripts/serve.py")
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
    assert commands == [("python", "scripts/serve.py")]
    assert "--force" not in commands[0]
    assert "restarted" in capsys.readouterr().out


def test_restart_emits_one_final_success_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        lifecycle_commands,
        "_prepare_frontend_for_launch",
        lambda *_args: None,
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
            status="stopped", command=("python", "scripts/serve.py")
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
    assert commands == [("python", "scripts/serve.py")]


def test_dispatch_propagates_lifecycle_failure(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        elfienest,
        "stop_background_service",
        lambda _lifecycle, **_kwargs: ServiceLifecycleResult(status="failed"),
    )

    # When / Then
    with pytest.raises(SystemExit) as error:
        elfienest._dispatch_command(
            Namespace(command="stop"),
            LIFECYCLE,
            selected_home=Path("/tmp/selected"),
        )
    assert error.value.code == 1


def test_web_opens_the_tracked_service_port(monkeypatch) -> None:
    # Given
    opened: list[str] = []
    runtime = RuntimeSnapshotV1(
        instance_id="tracked",
        generation=3,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", 8100),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 8768),
        ),
    )
    monkeypatch.setattr(LIFECYCLE, "runtime_snapshot", lambda *_args: runtime)
    monkeypatch.setattr(
        LIFECYCLE,
        "existing_service_command",
        lambda *args: (42, ("python", "scripts/serve.py", "--port", "8100")),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000, **_kwargs: port == 8100,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    # When
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then
    assert result.status == "already_running"
    assert opened == ["http://127.0.0.1:8100/"]


def test_web_uses_the_published_port_for_an_automatic_running_service(
    monkeypatch,
) -> None:
    opened: list[str] = []
    dynamic_runtime = RuntimeSnapshotV1(
        instance_id="automatic-instance",
        generation=5,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", 18234),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 18235),
        ),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "existing_service_command",
        lambda *args: (42, ("python", "scripts/serve.py")),
    )
    monkeypatch.setattr(LIFECYCLE, "runtime_snapshot", lambda *_args: dynamic_runtime)
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port, **_kwargs: port == 18234,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)

    result = lifecycle_commands.open_web_console(LIFECYCLE)

    assert result.status == "already_running"
    assert result.command == ("--port", "18234")
    assert opened == ["http://127.0.0.1:18234/"]


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


def test_product_start_options_enable_lan_by_default_and_allow_loopback() -> None:
    # Given
    default_start = Namespace(
        port=None,
        godot_ws_port=None,
        lan=True,
    )
    loopback_start = Namespace(
        port=None,
        godot_ws_port=None,
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
    health = RuntimeSnapshotV1(
        instance_id="tracked",
        generation=3,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", 8100),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 8768),
        ),
    ).projection()
    monkeypatch.setattr(LIFECYCLE, "runtime_projection", lambda *_args: health)
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
                "--godot-ws-port",
                "8768",
            ),
        ),
    )

    def fake_statuses(http_port: int, godot_ws_port: int):
        checked.extend(
            (
                (http_port, "HTTP"),
                (godot_ws_port, "WebSocket (Godot)"),
            )
        )
        return tuple(
            ServicePortStatus(port=port, name=name, running=True)
            for port, name in checked
        )

    monkeypatch.setattr(LIFECYCLE, "service_port_statuses", fake_statuses)
    # When
    lifecycle_commands.show_service_status(LIFECYCLE)

    # Then
    output = capsys.readouterr().out
    assert (8100, "HTTP") in checked
    assert (8768, "WebSocket (Godot)") in checked
    assert "port 8100" in output
    assert "port 8768" in output


def test_status_uses_published_ports_when_pid_receipt_is_missing(
    monkeypatch, capsys
) -> None:
    # Given: the Runtime snapshot is healthy on an automatically selected pair.
    health = RuntimeSnapshotV1(
        instance_id="published",
        generation=2,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", 18234),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 18235),
        ),
        owner_lease=OwnerLease("cli", 2),
    ).projection()
    checked: list[tuple[int, int]] = []
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(LIFECYCLE, "runtime_projection", lambda *_args: health)
    monkeypatch.setattr(
        LIFECYCLE,
        "default_port_statuses",
        lambda: pytest.fail("status must not fall back to default ports"),
    )
    monkeypatch.setattr(
        LIFECYCLE,
        "service_port_statuses",
        lambda http, ws: (
            checked.append((http, ws))
            or (
                ServicePortStatus(http, "HTTP", True),
                ServicePortStatus(ws, "WebSocket (Godot)", True),
            )
        ),
    )
    # When
    lifecycle_commands.show_service_status(LIFECYCLE)

    # Then
    assert checked == [(18234, 18235)]
    output = capsys.readouterr().out
    assert "port 18234" in output
    assert "✅ HTTP" in output
    assert "occupied by external process" not in output


def test_web_uses_published_http_endpoint_without_pid_receipt(monkeypatch) -> None:
    # Given: a healthy Runtime published a non-default HTTP endpoint.
    runtime = RuntimeSnapshotV1(
        instance_id="published",
        generation=2,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.NORMAL,
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", 18234),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", 18235),
        ),
    )
    health = runtime.projection()
    opened: list[str] = []
    checked: list[int] = []
    monkeypatch.setattr(LIFECYCLE, "existing_service_command", lambda *args: None)
    monkeypatch.setattr(LIFECYCLE, "runtime_snapshot", lambda *_args: runtime)
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *_args, **_kwargs: _LaunchSupervisor(health, []),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_web_is_healthy",
        lambda _lifecycle, port=8000, **_kwargs: checked.append(port) or port == 18234,
    )
    monkeypatch.setattr(lifecycle_commands.webbrowser, "open", opened.append)
    monkeypatch.setattr(
        LIFECYCLE,
        "default_port_statuses",
        lambda: pytest.fail("web must not inspect default ports"),
    )

    # When
    result = lifecycle_commands.open_web_console(LIFECYCLE)

    # Then
    assert result.status == "already_running"
    assert checked == [18234]
    assert opened == ["http://127.0.0.1:18234/"]
