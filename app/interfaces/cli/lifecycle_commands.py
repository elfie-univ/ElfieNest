"""User-visible service lifecycle commands."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.orchestration.lifecycle import (
    DEFAULT_GODOT_WS_PORT,
    DEFAULT_HTTP_PORT,
    AuthorityHostConfig,
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    DataHomeState,
    EndpointSnapshot,
    FrontendPreparationError,
    LaunchFailedError,
    LifecycleFacade,
    ModelHealthProjection,
    ModelOverallState,
    RuntimeComponent,
    RuntimeLifecycle,
    RuntimeObservation,
    RuntimePhase,
    RuntimeProgressPhase,
    RuntimeProjectionV1,
    RuntimeTarget,
    ServiceLifecycleResult,
    ServicePortsActiveError,
    http_port_from_command,
    service_ports_from_command,
    validate_service_ports,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_URL = "http://127.0.0.1:8000/"
WEB_HEALTH_URL = "http://127.0.0.1:8000/api/health"
BACKGROUND_START_TIMEOUT_SECONDS = 60.0
AUTHORITY_START_TIMEOUT_SECONDS = 120.0
CONTROLLER_STOP_TIMEOUT_SECONDS = 15.0


def _runtime_project_root() -> Path:
    """Resolve the installed application root before the source checkout default."""
    configured = os.environ.get("ELFIENEST_PROJECT_ROOT")
    return Path(configured).resolve() if configured else PROJECT_ROOT


def _supervisor_for(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    http_port: int,
    *,
    use_remembered_home: bool = False,
    automatic_ports: bool = False,
    progress_callback: Optional[Callable[[RuntimeProgressPhase], None]] = None,
) -> RuntimeLifecycle:
    """Build the one Runtime Supervisor used by source and installed CLI commands."""
    launch_command = tuple(command)
    selected_home = _data_home_for_command(
        lifecycle,
        launch_command,
        use_remembered_home=use_remembered_home,
    )
    _, godot_ws_port = service_ports_from_command(launch_command)
    generation_nonce = secrets.token_urlsafe(32)
    project_root = _runtime_project_root()
    child_environment = {
        "ELFIE_HOME": str(selected_home),
        "ELFIENEST_GODOT_NONCE": generation_nonce,
    }
    if automatic_ports:
        child_environment["ELFIENEST_PORT_MODE"] = "automatic"
    return lifecycle.runtime_supervisor(
        elfie_home=selected_home,
        project_root=project_root,
        launch_command=launch_command,
        authority_config=AuthorityHostConfig(
            project_root=project_root,
            http_port=http_port,
            ws_port=godot_ws_port,
            nonce=generation_nonce,
            core_pid_file=selected_home / "elfienest.pid",
        ),
        health_probe=lambda: _full_runtime_health(
            lifecycle,
            http_port,
            godot_ws_port,
            lambda: lifecycle.model_health_projection(selected_home),
            data_home=selected_home,
        ),
        authority_timeout_seconds=AUTHORITY_START_TIMEOUT_SECONDS,
        core_timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
        child_environment=child_environment,
        progress_callback=progress_callback,
    )


def _full_runtime_health(
    lifecycle: LifecycleFacade,
    port: int,
    godot_ws_port: int = DEFAULT_GODOT_WS_PORT,
    model_projection: ModelHealthProjection
    | Callable[[], ModelHealthProjection]
    | None = None,
    *,
    data_home: Path | None = None,
) -> RuntimeObservation:
    """Map bounded endpoint evidence into a lifecycle observation.

    Core/Gateway readiness deliberately does not depend on Godot or model
    readiness; those are separate convergence axes.
    """
    port, godot_ws_port = _published_runtime_ports(
        lifecycle,
        data_home,
        fallback_http=port,
        fallback_websocket=godot_ws_port,
    )
    failed = ComponentState.FAILED
    core = failed
    gateway = failed
    authority = failed
    core_detail = "Core health endpoint unavailable"
    gateway_detail = "Gateway readiness unavailable"
    authority_detail = "Godot authority handshake unavailable"
    try:
        response = lifecycle.http_get(
            f"http://127.0.0.1:{port}/api/health", timeout_seconds=2.0
        )
        payload = json.loads(response.body.decode("utf-8"))
        if (
            response.status == 200
            and isinstance(payload, dict)
            and payload.get("status") == "ok"
        ):
            engine_ready = payload.get("engine_ready") is True
            core = ComponentState.READY if engine_ready else failed
            gateway = ComponentState.READY if engine_ready else failed
            if engine_ready:
                core_detail = ""
                gateway_detail = ""
            authority = (
                ComponentState.READY
                if payload.get("godot_runtime_ready") is True
                else failed
            )
            if authority is ComponentState.READY:
                authority_detail = ""
    except (OSError, TimeoutError, ValueError):
        pass
    if callable(model_projection):
        try:
            projection = model_projection()
        except (OSError, RuntimeError, ValueError):
            projection = None
    else:
        projection = model_projection
    if projection is None:
        optional_ready = lifecycle.optional_component_ready()
        projection = ModelHealthProjection(
            state=(
                ModelOverallState.READY
                if optional_ready
                else ModelOverallState.DEGRADED
            ),
            common_state=(
                ModelOverallState.READY
                if optional_ready
                else ModelOverallState.DEGRADED
            ),
            emergency_state=(
                ModelOverallState.READY
                if optional_ready
                else ModelOverallState.UNAVAILABLE
            ),
        )
    ollama = projection.state
    return RuntimeObservation(
        components=(
            ComponentSnapshot(RuntimeComponent.CORE, core, detail=core_detail),
            ComponentSnapshot(RuntimeComponent.GATEWAY, gateway, detail=gateway_detail),
            ComponentSnapshot(
                RuntimeComponent.GODOT_AUTHORITY,
                authority,
                detail=authority_detail,
            ),
            ComponentSnapshot(
                RuntimeComponent.OLLAMA,
                ComponentState.READY
                if ollama is ModelOverallState.READY
                else ComponentState.DEGRADED,
            ),
        ),
        endpoints=(
            EndpointSnapshot("http", "http", "127.0.0.1", port),
            EndpointSnapshot("godot_ws", "ws", "127.0.0.1", godot_ws_port),
        )
        if core is ComponentState.READY
        else (),
        model_state=ollama,
        model_common_state=projection.common_state,
        model_emergency_state=projection.emergency_state,
        model_revision=projection.revision,
    )


def _published_runtime_ports(
    lifecycle: LifecycleFacade,
    data_home: Path | None,
    *,
    fallback_http: int,
    fallback_websocket: int,
) -> tuple[int, int]:
    """Read Core's atomically bound endpoint pair from the durable snapshot."""
    if data_home is None:
        return fallback_http, fallback_websocket
    try:
        snapshot = lifecycle.runtime_snapshot(data_home)
    except (AttributeError, OSError, RuntimeError, ValueError):
        return fallback_http, fallback_websocket
    endpoints = {
        endpoint.name: endpoint.port
        for endpoint in snapshot.endpoints
        if endpoint.port > 0
    }
    return (
        endpoints.get("http", fallback_http),
        endpoints.get("godot_ws", fallback_websocket),
    )


class ProgressIndicator:
    """Simple progress indicator with spinner animation."""

    def __init__(self, message: str = "Starting") -> None:
        self.message = message
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def _spin(self) -> None:
        idx = 0
        while self.running:
            spinner = self.spinner_chars[idx % len(self.spinner_chars)]
            print(f"\r  {spinner} {self.message}...", end="", flush=True)
            time.sleep(0.1)
            idx += 1

    def start(self) -> None:
        """Start the spinner animation."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(
        self,
        success: bool = True,
        *,
        message: Optional[str] = None,
    ) -> None:
        """Stop the spinner and show result."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        final_message = message or self.message
        print(
            f"\r  {'✅' if success else '❌'} {final_message}{' ✓' if success else ' ✗'}    ",
            flush=True,
        )


def _data_home_for_command(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    *,
    use_remembered_home: bool = False,
) -> Path:
    """从服务命令与已记录生命周期选择中解析数据根。"""
    explicit_home = _option_value(command, "--data-home")
    return lifecycle.select_data_home(
        explicit_home,
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        use_remembered=use_remembered_home,
    )


def _option_value(command: Sequence[str], option: str) -> Optional[str]:
    for index, argument in enumerate(command):
        if argument == option:
            value_index = index + 1
            if value_index >= len(command):
                raise ValueError(f"{option} requires a value")
            return command[value_index]
        prefix = f"{option}="
        if argument.startswith(prefix):
            return argument[len(prefix) :]
    return None


def _remember_lifecycle_data_home(
    lifecycle: LifecycleFacade, selected_home: Path
) -> None:
    """Ask the lifecycle boundary to persist the current checkout selection."""
    lifecycle.remember_data_home(
        selected_home,
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
    )


def _prepare_frontend_for_launch(lifecycle: LifecycleFacade) -> None:
    """Refresh the source Web bundle only for an explicit development launch."""
    runtime_mode = os.environ.get("ELFIENEST_RUNTIME_MODE")
    if runtime_mode != "development":
        return
    lifecycle.prepare_frontend(runtime_mode)


def _runtime_is_stably_running(supervisor: RuntimeLifecycle) -> bool:
    """Treat a leased Core/World generation as an idempotent running service."""
    projection = supervisor.status()
    return (
        projection.owner_lease is not None
        and projection.tier is not BackendTier.OFFLINE
    )


def _data_home_launch_error(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    *,
    use_remembered_home: bool,
) -> Optional[LaunchFailedError]:
    """Explain an unusable data root before the child process is spawned."""
    inspection = lifecycle.inspect_data_home(
        _option_value(command, "--data-home"),
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        use_remembered=use_remembered_home,
    )
    if inspection.state in {DataHomeState.FRESH, DataHomeState.READY}:
        return None
    guidance = (
        "；请先备份后重建。不会自动迁移或删除。" if inspection.recoverable else ""
    )
    return LaunchFailedError(f"Service startup blocked: {inspection.detail}{guidance}")


def _has_port_option(command: Sequence[str], option: str) -> bool:
    return any(
        argument == option or argument.startswith(f"{option}=") for argument in command
    )


def _select_automatic_ports(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    data_home: Path,
    *,
    avoid_pairs: Sequence[tuple[int, int]] = (),
) -> tuple[str, ...]:
    """Choose a stable per-data-root pair only for implicit default ports.

    Explicit ports remain strict and are handled by the typed conflict path.
    The selected pair is written into the child command, so every later
    status/stop operation uses the exact published endpoints.
    """
    selected = tuple(command)
    if _has_port_option(selected, "--port") or _has_port_option(
        selected, "--godot-ws-port"
    ):
        return selected
    try:
        occupied = lifecycle.ports_in_use((DEFAULT_HTTP_PORT, DEFAULT_GODOT_WS_PORT))
    except OSError:
        return selected
    if not occupied and not avoid_pairs:
        return selected
    try:
        if (
            lifecycle.existing_service_command(data_home, _runtime_project_root())
            is not None
        ):
            return selected
    except OSError:
        return selected
    digest = hashlib.sha256(str(data_home.resolve()).encode("utf-8")).digest()
    start = 12000 + int.from_bytes(digest[:2], "big") % 12000
    for offset in range(0, 2000, 2):
        http_port = start + offset
        ws_port = http_port + 1
        if ws_port > 65535:
            break
        if (http_port, ws_port) in avoid_pairs:
            continue
        try:
            if lifecycle.ports_in_use((http_port, ws_port)):
                continue
        except OSError:
            return selected
        return (*selected, "--port", str(http_port), "--godot-ws-port", str(ws_port))
    return selected


def _without_port_options(command: Sequence[str]) -> tuple[str, ...]:
    """Remove implicit endpoint choices before a bounded conflict retry."""
    result: list[str] = []
    skip_next = False
    for argument in command:
        if skip_next:
            skip_next = False
            continue
        if argument in {"--port", "--godot-ws-port"}:
            skip_next = True
            continue
        if argument.startswith("--port=") or argument.startswith("--godot-ws-port="):
            continue
        result.append(argument)
    return tuple(result)


def _is_automatic_port_conflict(result: ServiceLifecycleResult) -> bool:
    """Recognize only bind-conflict failures eligible for an endpoint retry."""
    if isinstance(result.error, ServicePortsActiveError):
        return True
    detail = str(result.error or "").lower()
    return (
        "address already in use" in detail or "port" in detail and "occupied" in detail
    )


def start_background_service(
    lifecycle: LifecycleFacade,
    command: Optional[Sequence[str]] = None,
    *,
    owner_id: str = "cli",
    json_output: bool = False,
    progress_json: bool = False,
) -> ServiceLifecycleResult:
    """Start the service once; a verified running process is left untouched."""
    if _should_start_packaged_controller():
        return _start_packaged_controller(
            lifecycle,
            command=command,
            json_output=json_output,
        )
    progress = (
        None if json_output or progress_json else ProgressIndicator("Starting service")
    )
    if progress is not None:
        progress.start()

    launch_command = (
        tuple(command)
        if command is not None
        else lifecycle.default_service_command(("--lan",))
    )
    implicit_ports = not _has_port_option(
        launch_command, "--port"
    ) and not _has_port_option(launch_command, "--godot-ws-port")
    try:
        http_port = _validated_http_port(launch_command)
    except ValueError as error:
        if progress is not None:
            progress.stop(success=False)
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"Invalid service port: {error}")
        )
        _print_start_result_or_json(lifecycle, result, json_output=json_output)
        return result
    progress_callback = (
        (lambda phase: _print_runtime_progress_json(phase)) if progress_json else None
    )
    supervisor = _supervisor_for(
        lifecycle,
        launch_command,
        http_port,
        use_remembered_home=True,
        automatic_ports=implicit_ports,
        progress_callback=progress_callback,
    )
    try:
        if not _runtime_is_stably_running(supervisor):
            data_home_error = _data_home_launch_error(
                lifecycle,
                launch_command,
                use_remembered_home=True,
            )
            if data_home_error is not None:
                if progress is not None:
                    progress.stop(success=False)
                result = ServiceLifecycleResult(
                    status="failed", command=launch_command, error=data_home_error
                )
                _print_start_result_or_json(lifecycle, result, json_output=json_output)
                return result
            selected_home = _data_home_for_command(
                lifecycle,
                launch_command,
                use_remembered_home=True,
            )
            selected_command = _select_automatic_ports(
                lifecycle,
                launch_command,
                selected_home,
            )
            if selected_command != launch_command:
                launch_command = selected_command
                http_port = _validated_http_port(launch_command)
                supervisor = _supervisor_for(
                    lifecycle,
                    launch_command,
                    http_port,
                    use_remembered_home=True,
                    automatic_ports=implicit_ports,
                    progress_callback=progress_callback,
                )
            _prepare_frontend_for_launch(lifecycle)
    except FrontendPreparationError as error:
        if progress is not None:
            progress.stop(success=False)
        result = ServiceLifecycleResult(
            status="failed",
            command=launch_command,
            error=LaunchFailedError(f"Frontend build failed: {error}"),
        )
        _print_start_result_or_json(lifecycle, result, json_output=json_output)
        return result
    attempted_ports: list[tuple[int, int]] = []
    result = supervisor.start(owner_id=owner_id)
    while (
        result.status == "failed"
        and implicit_ports
        and _is_automatic_port_conflict(result)
        and len(attempted_ports) < 2
    ):
        attempted_ports.append(service_ports_from_command(launch_command))
        retry_base = _without_port_options(launch_command)
        selected_home = _data_home_for_command(
            lifecycle,
            retry_base,
            use_remembered_home=True,
        )
        retry_command = _select_automatic_ports(
            lifecycle,
            retry_base,
            selected_home,
            avoid_pairs=attempted_ports,
        )
        if retry_command == retry_base:
            break
        launch_command = retry_command
        http_port = _validated_http_port(launch_command)
        supervisor = _supervisor_for(
            lifecycle,
            launch_command,
            http_port,
            use_remembered_home=True,
            automatic_ports=implicit_ports,
            progress_callback=progress_callback,
        )
        result = supervisor.start(owner_id=owner_id)
    if result.status in {"started", "already_running"}:
        try:
            _remember_lifecycle_data_home(
                lifecycle,
                _data_home_for_command(
                    lifecycle,
                    launch_command,
                    use_remembered_home=True,
                ),
            )
        except OSError as error:
            result = ServiceLifecycleResult(
                status="failed",
                pid=result.pid,
                command=result.command,
                error=LaunchFailedError(f"Cannot record selected data home: {error}"),
            )
    if progress is not None:
        progress.stop(success=result.status in {"started", "already_running"})
    _print_start_result_or_json(
        lifecycle,
        result,
        supervisor=supervisor,
        json_output=json_output,
    )
    return result


def stop_background_service(
    lifecycle: LifecycleFacade, owner_id: str = "cli"
) -> ServiceLifecycleResult:
    """Stop only the current project's verified service process."""
    selected_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        use_remembered_home=True,
    )
    if owner_id == "cli" and _should_start_packaged_controller():
        try:
            controller_result = lifecycle.controller_request("STOP_SERVER")
        except RuntimeError as error:
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Controller stop rejected: {error}"),
            )
            print(f"  ❌ Failed to stop service: {result.error}")
            return result
        if controller_result is not None:
            failure = _controller_failure_result(controller_result, "stop")
            if failure is not None:
                print(f"  ❌ Failed to stop service: {failure.error}")
                return failure
            if not _wait_for_runtime_offline(lifecycle, selected_home):
                result = ServiceLifecycleResult(
                    status="failed",
                    error=LaunchFailedError(
                        "Controller accepted stop but Runtime did not reach OFFLINE "
                        f"within {CONTROLLER_STOP_TIMEOUT_SECONDS:g} seconds"
                    ),
                )
                print(f"  ❌ Failed to stop service: {result.error}")
                return result
            desktop_result = lifecycle.stop_desktop(selected_home)
            if desktop_result.status == "failed":
                print(f"  ❌ Failed to stop service: {desktop_result.error}")
                return desktop_result
            print("  ✅ Service stopped")
            return ServiceLifecycleResult(status="stopped", pid=desktop_result.pid)

    supervisor = _supervisor_for(
        lifecycle,
        lifecycle.default_service_command(),
        DEFAULT_HTTP_PORT,
        use_remembered_home=True,
    )
    if owner_id != "cli":
        health = supervisor.status()
        owner_mismatch = (
            health.owner_lease is not None and health.owner_lease.owner_id != owner_id
        )
        startup_owner_mismatch = (
            health.startup_owner_id is not None and health.startup_owner_id != owner_id
        )
        if owner_mismatch or startup_owner_mismatch:
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    "Runtime owner lease does not allow this client to stop the service"
                ),
            )
            print(f"  ❌ Failed to stop service: {result.error}")
            return result
    result = supervisor.stop()
    if (
        result.status in {"stopped", "already_stopped"}
        and _should_start_packaged_controller()
    ):
        desktop_result = lifecycle.stop_desktop(selected_home)
        if desktop_result.status == "failed":
            result = desktop_result
    if result.status == "stopped":
        print("  ✅ Service stopped")
    elif result.status == "already_stopped":
        print("  ⭕ Service not running")
    else:
        print(f"  ❌ Failed to stop service: {result.error}")
    return result


def restart_background_service(lifecycle: LifecycleFacade) -> ServiceLifecycleResult:
    """Stop the current process and start it again with its existing arguments."""
    progress = ProgressIndicator("Restarting service")
    progress.start()

    default_command = lifecycle.default_service_command()
    data_home_error = _data_home_launch_error(
        lifecycle,
        default_command,
        use_remembered_home=True,
    )
    if data_home_error is not None:
        progress.stop(success=False, message="Service restart failed")
        result = ServiceLifecycleResult(status="failed", error=data_home_error)
        print(f"  ❌ Service restart failed: {result.error}")
        return result

    stop_supervisor = _supervisor_for(
        lifecycle,
        lifecycle.default_service_command(),
        DEFAULT_HTTP_PORT,
        use_remembered_home=True,
    )
    try:
        _prepare_frontend_for_launch(lifecycle)
    except FrontendPreparationError as error:
        progress.stop(success=False, message="Service restart failed")
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Frontend build failed: {error}"),
        )
        print(f"  ❌ Service restart failed: {result.error}")
        return result

    stopped = stop_supervisor.stop()
    if stopped.status == "failed":
        progress.stop(success=False, message="Service restart failed")
        print(f"  ❌ Cannot restart service: {stopped.error}")

        # Enhanced error message for port occupation
        if isinstance(stopped.error, ServicePortsActiveError):
            print()
            from app.interfaces.cli.doctor_commands import diagnose_ports

            occupied = diagnose_ports(lifecycle=lifecycle)
            if occupied:
                print("  ⚠️  Port occupation detected:")
                print()
                for port, proc_info in occupied.items():
                    print(f"  - Port {port}:")
                    print(f"    PID: {proc_info.pid}")
                    if proc_info.command:
                        cmd_str = " ".join(proc_info.command)
                        if len(cmd_str) > 80:
                            cmd_str = cmd_str[:77] + "..."
                        print(f"    Command: {cmd_str}")
                    if proc_info.cwd:
                        cwd_str = str(proc_info.cwd)
                        if len(cwd_str) > 80:
                            cwd_str = cwd_str[:77] + "..."
                        print(f"    Working directory: {cwd_str}")
                    print()
                print(
                    "  💡 Run 'elfienest doctor --fix-ports' to inspect the occupant, then choose an unused port"
                )

        return stopped
    command = stopped.command or lifecycle.default_service_command(("--lan",))
    try:
        http_port = _validated_http_port(command)
    except ValueError as error:
        progress.stop(success=False, message="Service restart failed")
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"Invalid service port: {error}")
        )
        print(f"  ❌ Service restart failed: {result.error}")
        return result
    launch_command = tuple(argument for argument in command if argument != "--force")
    automatic_ports = not _has_port_option(
        launch_command, "--port"
    ) and not _has_port_option(launch_command, "--godot-ws-port")
    result = _supervisor_for(
        lifecycle,
        launch_command,
        http_port,
        automatic_ports=automatic_ports,
    ).start(owner_id="cli")
    succeeded = result.status in {"started", "already_running"}
    if succeeded:
        try:
            _remember_lifecycle_data_home(
                lifecycle,
                _data_home_for_command(
                    lifecycle,
                    launch_command,
                    use_remembered_home=True,
                ),
            )
        except OSError as error:
            result = ServiceLifecycleResult(
                status="failed",
                pid=result.pid,
                command=result.command,
                error=LaunchFailedError(f"Cannot record selected data home: {error}"),
            )
            succeeded = False
    progress.stop(
        success=succeeded,
        message="Service restarted" if succeeded else "Service restart failed",
    )
    if not succeeded:
        print(f"  ❌ Service restart failed: {result.error}")

        # Enhanced error message for port occupation
        if isinstance(result.error, ServicePortsActiveError):
            print()
            from app.interfaces.cli.doctor_commands import diagnose_ports

            occupied = diagnose_ports(lifecycle=lifecycle)
            if occupied:
                print("  ⚠️  Port occupation detected:")
                print()
                for port, proc_info in occupied.items():
                    print(f"  - Port {port}:")
                    print(f"    PID: {proc_info.pid}")
                    if proc_info.command:
                        cmd_str = " ".join(proc_info.command)
                        if len(cmd_str) > 80:
                            cmd_str = cmd_str[:77] + "..."
                        print(f"    Command: {cmd_str}")
                    if proc_info.cwd:
                        cwd_str = str(proc_info.cwd)
                        if len(cwd_str) > 80:
                            cwd_str = cwd_str[:77] + "..."
                        print(f"    Working directory: {cwd_str}")
                    print()
                print(
                    "  💡 Run 'elfienest doctor --fix-ports' to inspect the occupant, then choose an unused port"
                )

    return result


def show_service_status(
    lifecycle: LifecycleFacade, *, json_output: bool = False
) -> None:
    """Print lifecycle state without duplicating usage/session statistics."""
    elfie_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        use_remembered_home=True,
    )
    running = lifecycle.existing_service_command(elfie_home, _runtime_project_root())
    status_command = (
        running[1] if running is not None else lifecycle.default_service_command()
    )
    status_port = http_port_from_command(status_command)
    health = _supervisor_for(
        lifecycle,
        status_command,
        status_port,
        use_remembered_home=running is None,
    ).status()
    if json_output:
        _print_runtime_health_json(health)
        return
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()
    published_ports = _published_service_ports(health)
    verified_current_runtime = running is not None or (
        health.tier is not BackendTier.OFFLINE and health.owner_lease is not None
    )
    if not verified_current_runtime:
        port_statuses = (
            lifecycle.service_port_statuses(*published_ports)
            if published_ports is not None
            else lifecycle.default_port_statuses()
        )
        external = _external_recorded_service(lifecycle, elfie_home)
        if external is not None:
            pid, cwd, _ = external
            print(f"  ⚠️  Registered PID {pid} from another ElfieNest checkout: {cwd}")
        elif any(port_status.running for port_status in port_statuses):
            print(
                "  ⚠️  Default service ports occupied by external process from another ElfieNest checkout; "
                "no verified service for current project."
            )
    else:
        if running is not None:
            _, command = running
            published_ports = _published_service_ports(health)
            ports = published_ports or service_ports_from_command(command)
            port_statuses = lifecycle.service_port_statuses(ports[0], ports[1])
        elif published_ports is not None:
            port_statuses = lifecycle.service_port_statuses(*published_ports)
        else:
            port_statuses = lifecycle.default_port_statuses()
    for port_status in port_statuses:
        is_current_project = verified_current_runtime
        state = (
            "running"
            if is_current_project and port_status.running
            else "occupied by external process"
            if port_status.running
            else "not running"
        )
        icon = (
            "✅"
            if is_current_project and port_status.running
            else "⚠️"
            if port_status.running
            else "⭕"
        )
        print(f"  {icon} {port_status.name}: {state} (port {port_status.port})")
    if health.components:
        print()
        print(f"  Runtime: {health.tier.value} (generation {health.generation})")
        for component in health.components:
            print(f"  - {component.component.value}: {component.state.value}")
        print(
            "  Model: "
            f"{health.model_state.value} "
            f"(common={health.model_common_state.value}, "
            f"emergency={health.model_emergency_state.value})"
        )
    print()


def open_web_console(lifecycle: LifecycleFacade) -> ServiceLifecycleResult:
    """Ensure a healthy service and open the Web management console."""
    default_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        use_remembered_home=True,
    )
    running = lifecycle.existing_service_command(default_home, _runtime_project_root())
    if running is not None:
        _, running_command = running
        port = http_port_from_command(running_command)
        if not _web_is_healthy(lifecycle, port):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    f"Registered service but Web port {port} failed health check"
                ),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
    else:
        published_ports = _published_service_ports(
            _supervisor_for(
                lifecycle,
                lifecycle.default_service_command(),
                DEFAULT_HTTP_PORT,
                use_remembered_home=True,
            ).status()
        )
        published_http_port = (
            published_ports[0] if published_ports is not None else None
        )
        probe_port = published_http_port or DEFAULT_HTTP_PORT
        if _web_is_healthy(lifecycle, probe_port):
            web_url = f"http://127.0.0.1:{probe_port}/"
            webbrowser.open(web_url)
            print(f"  🌐 Opened running Web console: {web_url}")
            print(
                "  ⚠️  Service not verified by current project PID receipt; start/restart won't take over."
            )
            return ServiceLifecycleResult(status="already_running")
        if any(
            port_status.running for port_status in lifecycle.default_port_statuses()
        ):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    "Default service ports occupied by external process and Web health check failed; "
                    "manage it from the owning checkout, or start current project with custom ports"
                ),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
        result = start_background_service(lifecycle)
        if result.status not in {"started", "already_running"}:
            return result
        port = http_port_from_command(
            result.command or lifecycle.default_service_command(("--lan",))
        )
        if not _web_is_healthy(lifecycle, port):
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(
                    f"Service started but Web port {port} failed health check"
                ),
            )
            print(f"  ❌ Cannot open Web console: {result.error}")
            return result
    web_url = f"http://127.0.0.1:{port}/"
    webbrowser.open(web_url)
    print(f"  🌐 Opened Web console: {web_url}")
    return ServiceLifecycleResult(status="already_running")


def start_desktop_application(lifecycle: LifecycleFacade) -> ServiceLifecycleResult:
    """Explicitly start the packaged Electron Desktop supervisor."""
    if _should_start_packaged_controller():
        try:
            controller_result = lifecycle.controller_request("ACTIVATE_VIEWER")
        except RuntimeError as error:
            result = ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Controller activation rejected: {error}"),
            )
            print(f"  ❌ Desktop failed to start: {result.error}")
            return result
        if controller_result is not None:
            failure = _controller_failure_result(controller_result, "activate Viewer")
            if failure is not None:
                print(f"  ❌ Desktop failed to start: {failure.error}")
                return failure
            print("  ✅ Desktop Viewer activated")
            return ServiceLifecycleResult(status="already_running")

    selected_home = lifecycle.select_data_home(
        None,
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
    )
    result = lifecycle.start_desktop(
        selected_home,
        _runtime_project_root(),
        health_checker=lambda: _controller_runtime_ready(lifecycle, selected_home),
    )
    if result.status in {"started", "already_running"}:
        print(f"  ✅ Desktop started (PID {result.pid})")
    else:
        print(f"  ❌ Desktop failed to start: {result.error}")
    return result


def _should_start_packaged_controller() -> bool:
    """Installed CLI owns a tray Controller; its internal calls do not."""
    return (
        bool(os.environ.get("ELFIENEST_DESKTOP_BIN"))
        and os.environ.get("ELFIENEST_CONTROLLER_CLIENT") != "1"
    )


def _start_packaged_controller(
    lifecycle: LifecycleFacade,
    *,
    command: Optional[Sequence[str]] = None,
    json_output: bool,
) -> ServiceLifecycleResult:
    """Ensure the installed Controller without opening its Viewer."""
    if command is not None and _option_value(command, "--data-home") is not None:
        result = ServiceLifecycleResult(
            status="failed",
            command=tuple(command),
            error=LaunchFailedError(
                "Installed elfienest start does not support --data-home; "
                "use 'elfienest data-home activate --data-home PATH' to choose "
                "the production data root, or './elfienest.sh start --data-home PATH' "
                "for an isolated development instance"
            ),
        )
        if json_output:
            _print_start_result_or_json(lifecycle, result, json_output=True)
        else:
            print(f"  ❌ Controller failed to start: {result.error}")
        return result
    try:
        controller_result = lifecycle.controller_request("ENSURE_SERVER")
    except RuntimeError as error:
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Controller start rejected: {error}"),
        )
        if json_output:
            _print_start_result_or_json(lifecycle, result, json_output=True)
        else:
            print(f"  ❌ Controller failed to start: {result.error}")
        return result
    if controller_result is not None:
        failure = _controller_failure_result(controller_result, "start")
        if failure is not None:
            if json_output:
                _print_start_result_or_json(lifecycle, failure, json_output=True)
            else:
                print(f"  ❌ Controller failed to start: {failure.error}")
            return failure
        selected_home = _data_home_for_command(
            lifecycle,
            lifecycle.default_service_command(("--lan",)),
            use_remembered_home=True,
        )
        if json_output:
            _print_runtime_health_json(lifecycle.runtime_projection(selected_home))
        else:
            print("  ⭕ Controller already running; Viewer remains closed")
        return ServiceLifecycleResult(status="already_running")

    launch_command = lifecycle.default_service_command(("--lan",))
    selected_home = _data_home_for_command(
        lifecycle,
        launch_command,
        use_remembered_home=True,
    )
    result = lifecycle.start_desktop(
        selected_home,
        _runtime_project_root(),
        health_checker=lambda: _controller_runtime_ready(lifecycle, selected_home),
        background=True,
        timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
    )
    if json_output:
        if result.status in {"started", "already_running"}:
            _print_runtime_health_json(
                lifecycle.runtime_snapshot(selected_home).projection()
            )
        else:
            _print_start_result_or_json(lifecycle, result, json_output=True)
    elif result.status == "started":
        print(f"  ✅ Controller started (PID {result.pid}); Viewer remains closed")
    elif result.status == "already_running":
        print(f"  ⭕ Controller already running (PID {result.pid})")
    else:
        print(f"  ❌ Controller failed to start: {result.error}")
    return result


def _controller_failure_result(
    controller_result: object,
    action: str,
) -> ServiceLifecycleResult | None:
    """Map a Controller's explicit failed state to the CLI lifecycle result."""
    if (
        not isinstance(controller_result, dict)
        or controller_result.get("state") != "failed"
    ):
        return None
    reason = controller_result.get("reason")
    detail = (
        reason
        if isinstance(reason, str) and reason
        else "Controller reported a failed state"
    )
    return ServiceLifecycleResult(
        status="failed",
        error=LaunchFailedError(f"Controller failed to {action}: {detail}"),
    )


def _wait_for_runtime_offline(
    lifecycle: LifecycleFacade,
    elfie_home: Path,
    *,
    timeout_seconds: float = CONTROLLER_STOP_TIMEOUT_SECONDS,
    poll_interval_seconds: float = 0.1,
) -> bool:
    """Wait for the Controller-owned Runtime to publish a confirmed OFFLINE state."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            snapshot = lifecycle.runtime_snapshot(elfie_home)
        except (OSError, RuntimeError, ValueError):
            return False
        if (
            snapshot.tier is BackendTier.OFFLINE
            and snapshot.owner_lease is None
            and snapshot.startup_owner_id is None
        ):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_seconds)


def _controller_runtime_ready(lifecycle: LifecycleFacade, elfie_home: Path) -> bool:
    """Use the authoritative snapshot, not a fixed HTTP port, as readiness."""
    try:
        return lifecycle.runtime_snapshot(elfie_home).tier is not BackendTier.OFFLINE
    except (OSError, RuntimeError, ValueError):
        return False


def _web_is_healthy(lifecycle: LifecycleFacade, port: int = 8000) -> bool:
    health_url = f"http://127.0.0.1:{port}/api/health"
    try:
        return lifecycle.http_get(health_url, timeout_seconds=2.0).status == 200
    except (OSError, TimeoutError):
        return False


def _published_service_ports(
    health: RuntimeProjectionV1,
) -> tuple[int, int] | None:
    """Return the actual endpoint pair published by the current snapshot."""
    by_name = {endpoint.name: endpoint.port for endpoint in health.endpoints}
    http_port = by_name.get("http")
    godot_ws_port = by_name.get("godot_ws")
    if http_port is None or godot_ws_port is None:
        return None
    if http_port <= 0 or godot_ws_port <= 0:
        return None
    return http_port, godot_ws_port


def _external_recorded_service(
    lifecycle: LifecycleFacade,
    elfie_home: Path,
) -> tuple[int, Path, tuple[str, ...]] | None:
    """Return a live recorded service that belongs to another checkout."""
    try:
        pid_result = lifecycle.recorded_pid(elfie_home)
    except OSError:
        return None
    if not isinstance(pid_result, int) or not lifecycle.process_exists(pid_result):
        return None
    try:
        snapshot = lifecycle.inspect_process(pid_result)
        cwd = snapshot.cwd.resolve()
        command = snapshot.command
    except (OSError, RuntimeError, ValueError):
        return None
    if cwd == _runtime_project_root().resolve():
        return None
    return pid_result, cwd, tuple(command)


def _validated_http_port(command: Sequence[str]) -> int:
    """Parse and validate HTTP/Godot ports before spawning a service process."""
    ports = service_ports_from_command(command)
    error = validate_service_ports(ports[0], ports[1])
    if error:
        raise ValueError(error)
    return ports[0]


def _print_start_result(
    lifecycle: LifecycleFacade, result: ServiceLifecycleResult
) -> None:
    if result.status == "started":
        print(f"  ✅ Service started (PID {result.pid})")
    elif result.status == "already_running":
        print(f"  ⭕ Service already running (PID {result.pid})")
    else:
        print(f"  ❌ Service failed to start: {result.error}")

        # Enhanced error message for port occupation
        if isinstance(result.error, ServicePortsActiveError):
            print()
            from app.interfaces.cli.doctor_commands import diagnose_ports

            occupied = diagnose_ports(lifecycle=lifecycle)
            if occupied:
                print("  ⚠️  Port occupation detected:")
                print()
                for port, proc_info in occupied.items():
                    print(f"  - Port {port}:")
                    print(f"    PID: {proc_info.pid}")
                    if proc_info.command:
                        cmd_str = " ".join(proc_info.command)
                        if len(cmd_str) > 80:
                            cmd_str = cmd_str[:77] + "..."
                        print(f"    Command: {cmd_str}")
                    if proc_info.cwd:
                        cwd_str = str(proc_info.cwd)
                        if len(cwd_str) > 80:
                            cwd_str = cwd_str[:77] + "..."
                        print(f"    Working directory: {cwd_str}")
                    print()
                print(
                    "  💡 Run 'elfienest doctor --fix-ports' to inspect the occupant, then choose an unused port"
                )
            else:
                print(
                    "  ℹ️  Service ports appear free but were occupied during startup."
                )
                print("     This might indicate a race condition or transient issue.")


def _runtime_health_payload(health: RuntimeProjectionV1) -> dict[str, object]:
    """Serialize the one lifecycle projection for machine clients."""
    return {
        "schema_version": health.schema_version,
        "instance_id": health.instance_id,
        "state": health.tier.value,
        "tier": health.tier.value,
        "phase": health.phase.value,
        "subphase": health.subphase,
        "generation": health.generation,
        "revision": health.revision,
        "desired_target": health.desired_target.value,
        "reached_target": (
            health.reached_target.value if health.reached_target is not None else None
        ),
        "model_state": health.model_state.value,
        "model_common_state": health.model_common_state.value,
        "model_emergency_state": health.model_emergency_state.value,
        "model_revision": health.model_revision,
        "correlation_id": health.correlation_id,
        "timings": [
            {
                "phase": timing.phase,
                "duration_ms": timing.duration_ms,
                "elapsed_ms": timing.elapsed_ms,
            }
            for timing in health.timings
        ],
        "protocol_versions": list(health.protocol_versions),
        "endpoints": [
            {
                "name": endpoint.name,
                "scheme": endpoint.scheme,
                "host": endpoint.host,
                "port": endpoint.port,
                "protocol_version": endpoint.protocol_version,
            }
            for endpoint in health.endpoints
        ],
        "failures": [
            {"code": failure.code, "detail": failure.detail, "phase": failure.phase}
            for failure in health.failures
        ],
        "owner_lease": (
            {
                "owner_id": health.owner_lease.owner_id,
                "generation": health.owner_lease.generation,
            }
            if health.owner_lease is not None
            else None
        ),
        "startup_owner_id": health.startup_owner_id,
        "components": [
            {
                "name": component.component.value,
                "state": component.state.value,
                "detail": component.detail,
                "pid": component.pid,
            }
            for component in health.components
        ],
    }


def _print_runtime_health_json(health: RuntimeProjectionV1) -> None:
    print(
        json.dumps(_runtime_health_payload(health), ensure_ascii=False, sort_keys=True)
    )


def _print_runtime_progress_json(phase: RuntimeProgressPhase) -> None:
    print(
        json.dumps(
            {"event": "runtime_progress", "phase": phase.value},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


def _print_start_result_or_json(
    lifecycle: LifecycleFacade,
    result: ServiceLifecycleResult,
    *,
    supervisor: RuntimeLifecycle | None = None,
    json_output: bool,
) -> None:
    """Keep the human CLI unchanged while exposing one machine-readable start result."""
    if not json_output:
        _print_start_result(lifecycle, result)
        return
    if result.status in {"started", "already_running"} and supervisor is not None:
        _print_runtime_health_json(supervisor.status())
        return
    print(
        json.dumps(
            {
                "state": BackendTier.OFFLINE.value,
                "tier": BackendTier.OFFLINE.value,
                "phase": RuntimePhase.FAILED.value,
                "schema_version": 1,
                "instance_id": "uninitialized",
                "revision": 0,
                "desired_target": RuntimeTarget.CORE.value,
                "reached_target": None,
                "model_state": ModelOverallState.UNAVAILABLE.value,
                "model_common_state": ModelOverallState.UNAVAILABLE.value,
                "model_emergency_state": ModelOverallState.UNAVAILABLE.value,
                "model_revision": None,
                "owner_lease": None,
                "startup_owner_id": None,
                "components": [],
                "endpoints": [],
                "failures": [],
                "error": str(result.error)
                if result.error is not None
                else "start failed",
                "operation_id": result.operation_id,
                "generation": result.generation,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
