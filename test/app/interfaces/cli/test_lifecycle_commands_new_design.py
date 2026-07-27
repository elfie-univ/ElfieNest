from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from app.features.administration.system_service import PortStatus
from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.types import ServiceLifecycleResult
from scripts import elfienest


@pytest.fixture(autouse=True)
def isolated_lifecycle_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI lifecycle tests out of the developer's production ELFIE_HOME."""
    monkeypatch.setattr(lifecycle_commands, "get_elfie_home", lambda: tmp_path / "home")


def test_lifecycle_commands_use_repository_root_for_service_command() -> None:
    # Given
    repo_root = Path(__file__).resolve().parents[4]

    # When
    command = lifecycle_commands.default_service_command()

    # Then
    assert lifecycle_commands.PROJECT_ROOT == repo_root
    assert command[1] == str(repo_root / "scripts" / "serve.py")


def test_supervisor_shares_one_generation_nonce_without_persisting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one lifecycle generation starts Core and its hidden authority host.
    core_environments: list[dict[str, str]] = []
    authority_requests = []
    authority = type("AuthorityProcess", (), {"pid": 18171})()
    ready = RuntimeHealth(
        state=RuntimeHealthState.READY,
        generation=0,
        owner_lease=None,
        components=(
            ComponentHealth(RuntimeComponent.CORE, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.GATEWAY, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.GODOT_AUTHORITY, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.OLLAMA, RuntimeHealthState.FAILED),
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands.secrets, "token_urlsafe", lambda _n: "one-nonce"
    )
    monkeypatch.setattr(lifecycle_commands, "get_elfie_home", lambda: tmp_path / "home")
    monkeypatch.setattr(lifecycle_commands, "_full_runtime_health", lambda _port: ready)
    monkeypatch.setattr(
        lifecycle_commands,
        "authority_lifecycle",
        lambda request: (
            authority_requests.append(request) or (lambda: authority),
            lambda _process: None,
        ),
    )

    def fake_start_service(*_args, **kwargs):
        core_environments.append(dict(kwargs["child_environment"]))
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "elfienest.pid").write_text("18170", encoding="utf-8")
        return ServiceLifecycleResult(
            status="started", pid=18170, command=tuple(kwargs["command"])
        )

    monkeypatch.setattr(lifecycle_commands, "start_service", fake_start_service)
    monkeypatch.setattr(
        lifecycle_commands,
        "stop_service",
        lambda *_args, **_kwargs: ServiceLifecycleResult(status="stopped", pid=18170),
    )
    monkeypatch.setattr(
        lifecycle_commands, "_start_configured_public_ollama", lambda: None
    )
    command = lifecycle_commands.default_service_command(
        ("--port", "18170", "--godot-ws-port", "18171")
    )

    # When: the supervisor starts and writes its public Runtime receipt.
    supervisor = lifecycle_commands._supervisor_for(command, 18170)
    result = supervisor.start(owner_id="cli")

    # Then: Core and authority share one secret, while argv and receipt omit it.
    assert result.status == "started"
    assert core_environments == [{"ELFIENEST_GODOT_NONCE": "one-nonce"}]
    assert authority_requests[0].nonce == "one-nonce"
    assert authority_requests[0].http_port == 18170
    assert authority_requests[0].ws_port == 18171
    assert all("one-nonce" not in argument for argument in command)
    receipt = (tmp_path / "home/runtime.json").read_text(encoding="utf-8")
    assert "one-nonce" not in receipt


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
    assert "已在运行" in capsys.readouterr().out


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
    assert "端口" in capsys.readouterr().out


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
        lambda *args: ServiceLifecycleResult(
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
        lambda *args, **kwargs: ServiceLifecycleResult(
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
    assert "服务状态" in capsys.readouterr().out


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
    assert (8100, "HTTP 服务") in checked
    assert (8866, "WebSocket (管理)") in checked
    assert (8768, "WebSocket (Godot)") in checked
    assert "端口 8100" in output
    assert "端口 8866" in output


def test_status_json_reports_component_graph(monkeypatch, capsys) -> None:
    # Given
    from app.orchestration.lifecycle.runtime_health import (
        ComponentHealth,
        OwnerLease,
        RuntimeComponent,
        RuntimeHealth,
        RuntimeHealthState,
    )

    health = RuntimeHealth(
        state=RuntimeHealthState.DEGRADED,
        generation=4,
        owner_lease=OwnerLease(owner_id="cli", generation=4),
        components=(
            ComponentHealth(RuntimeComponent.CORE, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.OLLAMA, RuntimeHealthState.FAILED),
        ),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *args: type("Supervisor", (), {"status": lambda self: health})(),
    )

    # When
    lifecycle_commands.show_service_status(json_output=True)

    # Then
    output = capsys.readouterr().out
    assert '"generation": 4' in output
    assert '"name": "ollama"' in output


def test_status_probes_the_tracked_custom_runtime_ports(monkeypatch, capsys) -> None:
    # Given: the owned Core receipt records non-default ports.
    command = (
        "python",
        "scripts/serve.py",
        "--port",
        "18190",
        "--godot-ws-port",
        "18191",
        "--ws-port",
        "18192",
    )
    observed: list[tuple[tuple[str, ...], int]] = []
    health = RuntimeHealth(
        state=RuntimeHealthState.READY,
        generation=2,
        owner_lease=None,
        components=(),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "existing_service_command",
        lambda *_args: (18190, command),
    )
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda selected, port: (
            observed.append((tuple(selected), port))
            or type("Supervisor", (), {"status": lambda self: health})()
        ),
    )

    # When: JSON status is requested from a new CLI invocation.
    lifecycle_commands.show_service_status(json_output=True)

    # Then: it probes the ports from the tracked service instead of defaults.
    assert observed == [(command, 18190)]
    assert '"state": "ready"' in capsys.readouterr().out


def test_lease_scoped_stop_rejects_a_runtime_owned_by_another_client(
    monkeypatch,
) -> None:
    # Given: a CLI owns the active Runtime generation.
    from app.orchestration.lifecycle.runtime_health import (
        OwnerLease,
        RuntimeHealth,
        RuntimeHealthState,
    )

    health = RuntimeHealth(
        state=RuntimeHealthState.READY,
        generation=9,
        owner_lease=OwnerLease(owner_id="cli", generation=9),
        components=(),
    )
    stopped: list[str] = []
    monkeypatch.setattr(
        lifecycle_commands,
        "_supervisor_for",
        lambda *args: type(
            "Supervisor",
            (),
            {
                "status": lambda self: health,
                "stop": lambda self: (
                    stopped.append("stop") or ServiceLifecycleResult(status="stopped")
                ),
            },
        )(),
    )

    # When: a Desktop lease requests the ordered stop.
    result = lifecycle_commands.stop_background_service(owner_id="desktop-9")

    # Then: the CLI-owned Runtime remains untouched.
    assert result.status == "failed"
    assert stopped == []
