"""User-visible service lifecycle commands."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.orchestration.lifecycle import (
    DEFAULT_HTTP_PORT,
    AuthorityHostConfig,
    ComponentHealth,
    DataHomeState,
    FrontendPreparationError,
    LaunchFailedError,
    LifecycleFacade,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
    RuntimeLifecycle,
    RuntimeProgressPhase,
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
        health_probe=lambda: _full_runtime_health(lifecycle, http_port),
        prepare_optional_component=lifecycle.prepare_optional_component,
        authority_timeout_seconds=AUTHORITY_START_TIMEOUT_SECONDS,
        core_timeout_seconds=BACKGROUND_START_TIMEOUT_SECONDS,
        child_environment={
            "ELFIE_HOME": str(selected_home),
            "ELFIENEST_GODOT_NONCE": generation_nonce,
        },
        progress_callback=progress_callback,
    )


def _full_runtime_health(lifecycle: LifecycleFacade, port: int) -> RuntimeHealth:
    """Probe every Runtime component; an HTTP 200 alone is never ready."""
    failed = RuntimeHealthState.FAILED
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
            and payload.get("godot_web_ready") is True
        ):
            engine_ready = payload.get("engine_ready") is True
            core = RuntimeHealthState.READY if engine_ready else failed
            gateway = RuntimeHealthState.READY if engine_ready else failed
            if engine_ready:
                core_detail = ""
                gateway_detail = ""
            authority = (
                RuntimeHealthState.READY
                if payload.get("godot_runtime_ready") is True
                else failed
            )
            if authority is RuntimeHealthState.READY:
                authority_detail = ""
    except (OSError, TimeoutError, ValueError):
        pass
    ollama = (
        RuntimeHealthState.READY
        if lifecycle.optional_component_ready()
        else RuntimeHealthState.FAILED
    )
    return RuntimeHealth(
        state=RuntimeHealthState.STARTING,
        generation=0,
        owner_lease=None,
        components=(
            ComponentHealth(RuntimeComponent.CORE, core, detail=core_detail),
            ComponentHealth(RuntimeComponent.GATEWAY, gateway, detail=gateway_detail),
            ComponentHealth(
                RuntimeComponent.GODOT_AUTHORITY,
                authority,
                detail=authority_detail,
            ),
            ComponentHealth(RuntimeComponent.OLLAMA, ollama),
        ),
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
    """Treat a leased ready/degraded generation as an idempotent running service."""
    health = supervisor.status()
    return health.owner_lease is not None and health.state in {
        RuntimeHealthState.READY,
        RuntimeHealthState.DEGRADED,
    }


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


def start_background_service(
    lifecycle: LifecycleFacade,
    command: Optional[Sequence[str]] = None,
    *,
    owner_id: str = "cli",
    json_output: bool = False,
    progress_json: bool = False,
) -> ServiceLifecycleResult:
    """Start the service once; a verified running process is left untouched."""
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
                    "  💡 Run 'elfienest doctor --fix-ports' to diagnose and clean occupied ports"
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
    result = _supervisor_for(lifecycle, launch_command, http_port).start(owner_id="cli")
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
                    "  💡 Run 'elfienest doctor --fix-ports' to diagnose and clean occupied ports"
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
    if running is None and health.state in {
        RuntimeHealthState.STOPPED,
        RuntimeHealthState.FAILED,
    }:
        external_health = _attachable_external_runtime_health(lifecycle, status_port)
        if external_health is not None:
            health = external_health
    if json_output:
        _print_runtime_health_json(health)
        return
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()
    if running is None:
        port_statuses = lifecycle.default_port_statuses()
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
        _, command = running
        ports = service_ports_from_command(command)
        port_statuses = lifecycle.service_port_statuses(ports[0], ports[1])
    for port_status in port_statuses:
        is_current_project = running is not None
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
        print(f"  Runtime: {health.state.value} (generation {health.generation})")
        for component in health.components:
            print(f"  - {component.component.value}: {component.state.value}")
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
        if _web_is_healthy(lifecycle, 8000):
            webbrowser.open(WEB_URL)
            print(f"  🌐 Opened running Web console: {WEB_URL}")
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
    result = lifecycle.start_desktop(
        lifecycle.select_data_home(
            None,
            project_root=_runtime_project_root(),
            runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
        ),
        _runtime_project_root(),
        health_checker=lambda: _web_is_healthy(lifecycle),
    )
    if result.status in {"started", "already_running"}:
        print(f"  ✅ Desktop started (PID {result.pid})")
    else:
        print(f"  ❌ Desktop failed to start: {result.error}")
    return result


def _web_is_healthy(lifecycle: LifecycleFacade, port: int = 8000) -> bool:
    health_url = f"http://127.0.0.1:{port}/api/health"
    try:
        return lifecycle.http_get(health_url, timeout_seconds=2.0).status == 200
    except (OSError, TimeoutError):
        return False


def _attachable_external_runtime_health(
    lifecycle: LifecycleFacade,
    port: int,
) -> RuntimeHealth | None:
    """Map a verified ElfieNest Core owned elsewhere to a non-owned attachment."""
    observed = _full_runtime_health(lifecycle, port)
    components = {item.component: item.state for item in observed.components}
    if any(
        components.get(component) is not RuntimeHealthState.READY
        for component in (RuntimeComponent.CORE, RuntimeComponent.GATEWAY)
    ):
        return None
    full_runtime_ready = all(
        components.get(component) is RuntimeHealthState.READY
        for component in (
            RuntimeComponent.CORE,
            RuntimeComponent.GATEWAY,
            RuntimeComponent.GODOT_AUTHORITY,
            RuntimeComponent.OLLAMA,
        )
    )
    return RuntimeHealth(
        state=(
            RuntimeHealthState.READY
            if full_runtime_ready
            else RuntimeHealthState.DEGRADED
        ),
        generation=0,
        owner_lease=None,
        components=observed.components,
    )


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
                    "  💡 Run 'elfienest doctor --fix-ports' to diagnose and clean occupied ports"
                )
            else:
                print(
                    "  ℹ️  Service ports appear free but were occupied during startup."
                )
                print("     This might indicate a race condition or transient issue.")


def _runtime_health_payload(health: RuntimeHealth) -> dict[str, object]:
    """Serialize one lifecycle health snapshot for machine clients."""
    return {
        "state": health.state.value,
        "generation": health.generation,
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


def _print_runtime_health_json(health: RuntimeHealth) -> None:
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
                "state": RuntimeHealthState.FAILED.value,
                "generation": 0,
                "owner_lease": None,
                "startup_owner_id": None,
                "components": [],
                "error": str(result.error)
                if result.error is not None
                else "start failed",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
