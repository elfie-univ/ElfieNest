"""User-visible service lifecycle commands."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator, Optional, Sequence

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

if TYPE_CHECKING:
    from app.interfaces.cli.doctor_commands import ProcessInfo

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKGROUND_START_TIMEOUT_SECONDS = 60.0
AUTHORITY_START_TIMEOUT_SECONDS = 120.0
CONTROLLER_STOP_TIMEOUT_SECONDS = 15.0
_DISPLAY_DATA_HOME: ContextVar[Optional[str]] = ContextVar(
    "elfienest_display_data_home", default=None
)


def _runtime_project_root() -> Path:
    """Resolve the installed application root before the source checkout default."""
    configured = os.environ.get("ELFIENEST_PROJECT_ROOT")
    return Path(configured).resolve() if configured else PROJECT_ROOT


def _supervisor_for(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    http_port: int,
    *,
    selected_home: Path | None = None,
    automatic_ports: bool = False,
    progress_callback: Optional[Callable[[RuntimeProgressPhase], None]] = None,
) -> RuntimeLifecycle:
    """Build the one Runtime Supervisor used by source and installed CLI commands."""
    launch_command = tuple(command)
    selected_home = selected_home or _data_home_for_command(
        lifecycle,
        launch_command,
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


def _owned_core_health_matches(
    lifecycle: LifecycleFacade,
    selected_home: Path,
    *,
    expected_instance_id: str,
    expected_generation: int,
) -> bool:
    """Recheck the exact Core generation immediately before recovery."""
    http_port, _ = _published_runtime_ports(
        lifecycle,
        selected_home,
        fallback_http=DEFAULT_HTTP_PORT,
        fallback_websocket=DEFAULT_GODOT_WS_PORT,
    )
    try:
        response = lifecycle.http_get(
            f"http://127.0.0.1:{http_port}/api/health",
            timeout_seconds=2.0,
        )
        payload = json.loads(response.body.decode("utf-8"))
    except (OSError, TimeoutError, UnicodeDecodeError, ValueError):
        return False
    return (
        response.status == 200
        and isinstance(payload, dict)
        and payload.get("status") == "ok"
        and payload.get("engine_ready") is True
        and payload.get("instance_id") == expected_instance_id
        and payload.get("generation") == expected_generation
    )


def recover_owned_runtime_command(
    lifecycle: LifecycleFacade,
    *,
    selected_home: Path,
    owner_id: str,
    expected_instance_id: str,
    expected_generation: int,
    expected_core_pid: int | None,
    reason: str,
) -> int:
    """Run one fail-closed, lease-scoped recovery for Desktop Controller."""
    launch_command = lifecycle.default_service_command(("--lan",))
    supervisor = _supervisor_for(
        lifecycle,
        launch_command,
        _validated_http_port(launch_command),
        selected_home=selected_home,
        automatic_ports=True,
    )
    result = supervisor.recover_owned(
        owner_id=owner_id,
        expected_instance_id=expected_instance_id,
        expected_generation=expected_generation,
        expected_core_pid=expected_core_pid,
        health_check=lambda: _owned_core_health_matches(
            lifecycle,
            selected_home,
            expected_instance_id=expected_instance_id,
            expected_generation=expected_generation,
        ),
    )
    if result.status not in {"started", "already_running"}:
        print(
            json.dumps(
                {
                    "error_code": "owned_runtime_recovery_failed",
                    "error": str(result.error or "Owned Runtime recovery failed"),
                    "reason": reason,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    try:
        projection = lifecycle.runtime_projection(selected_home)
    except (OSError, RuntimeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "error_code": "owned_runtime_projection_failed",
                    "error": str(error),
                    "reason": reason,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    _print_runtime_health_json(projection, data_root=selected_home)
    return 0


def wait_for_runtime_command(
    lifecycle: LifecycleFacade,
    *,
    selected_home: Path,
    expected_instance_id: str,
    expected_generation: int,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.25,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    """Wait in one CLI process for an already-starting Runtime generation."""
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            projection = lifecycle.runtime_projection(selected_home)
        except (OSError, RuntimeError, ValueError) as error:
            print(
                json.dumps(
                    {
                        "error_code": "runtime_wait_snapshot_failed",
                        "error": str(error),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        if (
            projection.instance_id != expected_instance_id
            or projection.generation != expected_generation
        ):
            print(
                json.dumps(
                    {
                        "error_code": "runtime_wait_identity_changed",
                        "error": "Runtime identity changed while Desktop was waiting",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        if projection.phase is not RuntimePhase.CORE_STARTING:
            _print_runtime_health_json(projection, data_root=selected_home)
            return 0
        if monotonic() >= deadline:
            _print_runtime_health_json(projection, data_root=selected_home)
            return 0
        sleeper(poll_interval_seconds)


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
        clear_only: bool = False,
    ) -> None:
        """Stop the spinner and show result."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        if clear_only:
            print("\r" + (" " * 96) + "\r", end="", flush=True)
            return
        final_message = message or self.message
        print(
            f"\r  {'✅' if success else '❌'} {final_message}{' ✓' if success else ' ✗'}    ",
            flush=True,
        )


def _data_home_for_command(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    *,
    selected_home: Path | None = None,
) -> Path:
    """Use the dispatcher target, with legacy resolution for direct callers."""
    if selected_home is not None:
        return selected_home
    explicit_home = _option_value(command, "--data-home")
    return lifecycle.select_data_home(
        explicit_home,
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
    )


def selected_runtime_data_home(
    lifecycle: LifecycleFacade,
    *,
    selected_home: Path | None = None,
) -> Path:
    """Return the root published by the current command scope."""
    return _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        selected_home=selected_home,
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


@contextmanager
def _frontend_build_output(*, show_output: bool) -> Iterator[None]:
    """Scope the legacy frontend build-output switch to one CLI operation."""
    variable = "ELFIENEST_INTERACTIVE"
    previous = os.environ.get(variable)
    if show_output:
        os.environ.pop(variable, None)
    else:
        os.environ[variable] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = previous


def _prepare_frontend_for_launch(
    lifecycle: LifecycleFacade,
    *,
    show_output: bool = False,
) -> None:
    """Refresh the source Web bundle with command-appropriate output."""
    runtime_mode = os.environ.get("ELFIENEST_RUNTIME_MODE")
    if runtime_mode != "development":
        return
    with _frontend_build_output(show_output=show_output):
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
    selected_home: Path | None = None,
) -> Optional[LaunchFailedError]:
    """Explain an unusable data root before the child process is spawned."""
    explicit_home = (
        str(selected_home)
        if selected_home is not None
        else _option_value(command, "--data-home")
    )
    inspection = lifecycle.inspect_data_home(
        explicit_home,
        project_root=_runtime_project_root(),
        runtime_mode=os.environ.get("ELFIENEST_RUNTIME_MODE", "development"),
    )
    if inspection.state in {
        DataHomeState.FRESH,
        DataHomeState.PARTIAL,
        DataHomeState.READY,
    }:
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
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Start the service once; a verified running process is left untouched."""
    if _should_start_packaged_controller():
        return _start_packaged_controller(
            lifecycle,
            command=command,
            json_output=json_output,
            selected_home=selected_home,
        )
    launch_command = (
        tuple(command)
        if command is not None
        else lifecycle.default_service_command(("--lan",))
    )
    selected_home = _data_home_for_command(
        lifecycle,
        launch_command,
        selected_home=selected_home,
    )
    implicit_ports = not _has_port_option(
        launch_command, "--port"
    ) and not _has_port_option(launch_command, "--godot-ws-port")
    try:
        http_port = _validated_http_port(launch_command)
    except ValueError as error:
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"Invalid service port: {error}")
        )
        if not (json_output or progress_json):
            _print_lifecycle_intent(
                "start",
                selected_home,
                command=launch_command,
            )
        _print_start_result_or_json(
            lifecycle,
            result,
            json_output=json_output,
            selected_home=selected_home,
            action="start",
            compact=not (json_output or progress_json),
        )
        return result
    progress_callback = (
        (lambda phase: _print_runtime_progress_json(phase)) if progress_json else None
    )
    supervisor = _supervisor_for(
        lifecycle,
        launch_command,
        http_port,
        selected_home=selected_home,
        automatic_ports=implicit_ports,
        progress_callback=progress_callback,
    )
    running_before_start = _runtime_is_stably_running(supervisor)
    data_home_error = None
    if not running_before_start:
        data_home_error = _data_home_launch_error(
            lifecycle,
            launch_command,
            selected_home=selected_home,
        )
        if data_home_error is None:
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
                    selected_home=selected_home,
                    automatic_ports=implicit_ports,
                    progress_callback=progress_callback,
                )
    progress = (
        None if json_output or progress_json else ProgressIndicator("Starting service")
    )
    if progress is not None and not (json_output or progress_json):
        _print_lifecycle_intent(
            "start",
            selected_home,
            projection=_safe_runtime_projection(lifecycle, selected_home),
            command=launch_command,
        )
        progress.start()

    if data_home_error is not None:
        if progress is not None:
            progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(
            status="failed",
            command=launch_command,
            error=data_home_error,
        )
        _print_start_result_or_json(
            lifecycle,
            result,
            json_output=json_output,
            selected_home=selected_home,
            action="start",
            compact=not (json_output or progress_json),
        )
        return result

    try:
        if not running_before_start:
            _prepare_frontend_for_launch(lifecycle)
    except FrontendPreparationError as error:
        if progress is not None:
            progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(
            status="failed",
            command=launch_command,
            error=LaunchFailedError(f"Frontend build failed: {error}"),
        )
        _print_start_result_or_json(
            lifecycle,
            result,
            json_output=json_output,
            selected_home=selected_home,
            action="start",
            compact=not (json_output or progress_json),
        )
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
            selected_home=selected_home,
            automatic_ports=implicit_ports,
            progress_callback=progress_callback,
        )
        result = supervisor.start(owner_id=owner_id)
    if progress is not None:
        progress.stop(
            success=result.status in {"started", "already_running"},
            clear_only=True,
        )
    _print_start_result_or_json(
        lifecycle,
        result,
        supervisor=supervisor,
        json_output=json_output,
        selected_home=selected_home,
        action="start",
        compact=not (json_output or progress_json),
    )
    return result


def stop_background_service(
    lifecycle: LifecycleFacade,
    owner_id: str = "cli",
    *,
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Stop only the current project's verified service process."""
    selected_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        selected_home=selected_home,
    )
    before_projection = _safe_runtime_projection(lifecycle, selected_home)
    packaged = _should_start_packaged_controller()
    progress = None if packaged else ProgressIndicator("Stopping service")
    if progress is not None:
        _print_lifecycle_intent(
            "stop",
            selected_home,
            projection=before_projection,
            command=lifecycle.default_service_command(),
        )
        progress.start()
    if owner_id == "cli" and packaged:
        try:
            controller_result = lifecycle.controller_request(
                "STOP_SERVER", expected_data_home=selected_home
            )
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
        selected_home=selected_home,
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
            if progress is not None:
                progress.stop(success=False, clear_only=True)
                _print_lifecycle_result(
                    "stop",
                    selected_home,
                    result,
                    projection=_safe_runtime_projection(lifecycle, selected_home),
                    before_projection=before_projection,
                    command=lifecycle.default_service_command(),
                )
            else:
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
    if progress is not None:
        progress.stop(success=result.status != "failed", clear_only=True)
        _print_lifecycle_result(
            "stop",
            selected_home,
            result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
            before_projection=before_projection,
            command=lifecycle.default_service_command(),
        )
    elif result.status == "stopped":
        print("  ✅ Service stopped")
    elif result.status == "already_stopped":
        print("  ⭕ Service not running")
    else:
        print(f"  ❌ Failed to stop service: {result.error}")
    return result


def restart_background_service(
    lifecycle: LifecycleFacade,
    options: Sequence[str] = (),
    *,
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Stop the selected process and start it again with the requested options."""
    progress = ProgressIndicator("Restarting service")
    default_command = lifecycle.default_service_command(options)
    selected_home = _data_home_for_command(
        lifecycle,
        default_command,
        selected_home=selected_home,
    )
    before_projection = _safe_runtime_projection(lifecycle, selected_home)

    if not _should_start_packaged_controller():
        _print_lifecycle_intent(
            "restart",
            selected_home,
            projection=before_projection,
            command=default_command,
        )
    progress.start()

    if _should_start_packaged_controller():
        stopped = stop_background_service(lifecycle, selected_home=selected_home)
        if stopped.status not in {"stopped", "already_stopped"}:
            progress.stop(success=False, message="Service restart failed")
            print(f"  ❌ Cannot restart service: {stopped.error}")
            return stopped
        restarted = _start_packaged_controller(
            lifecycle,
            command=None,
            json_output=False,
            selected_home=selected_home,
        )
        succeeded = restarted.status in {"started", "already_running"}
        progress.stop(
            success=succeeded,
            message="Service restarted" if succeeded else "Service restart failed",
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="restart",
            result=restarted,
            projection=_safe_runtime_projection(lifecycle, selected_home),
        )
        if not succeeded:
            print(f"  ❌ Service restart failed: {restarted.error}")
        return restarted

    data_home_error = _data_home_launch_error(
        lifecycle,
        default_command,
        selected_home=selected_home,
    )
    if data_home_error is not None:
        progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(status="failed", error=data_home_error)
        _print_lifecycle_result(
            "restart",
            selected_home,
            result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
            before_projection=before_projection,
            command=default_command,
        )
        return result

    stop_supervisor = _supervisor_for(
        lifecycle,
        lifecycle.default_service_command(),
        DEFAULT_HTTP_PORT,
        selected_home=selected_home,
    )
    stopped = stop_supervisor.stop()
    if stopped.status == "failed":
        progress.stop(success=False, clear_only=True)
        _print_lifecycle_result(
            "restart",
            selected_home,
            stopped,
            projection=_safe_runtime_projection(lifecycle, selected_home),
            before_projection=before_projection,
            command=default_command,
        )

        # Enhanced error message for port occupation
        if isinstance(stopped.error, ServicePortsActiveError):
            print()
            occupied = _diagnose_ports_for_command(
                lifecycle,
                stopped.command or default_command,
                selected_home=selected_home,
                projection=before_projection,
            )
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
                    "  💡 Stop the exact task owning these ports, or start with an unused explicit port pair"
                )

        return stopped
    try:
        _prepare_frontend_for_launch(lifecycle)
    except FrontendPreparationError as error:
        progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Frontend build failed: {error}"),
        )
        _print_lifecycle_result(
            "restart",
            selected_home,
            result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
            before_projection=before_projection,
            command=default_command,
        )
        return result
    command = stopped.command or lifecycle.default_service_command(("--lan",))
    explicit_ports = _has_port_option(default_command, "--port") or _has_port_option(
        default_command, "--godot-ws-port"
    )
    try:
        if explicit_ports:
            launch_base = tuple(default_command)
            automatic_ports = False
        else:
            launch_base = _without_port_options(tuple(command))
            automatic_ports = True
        # A restart without explicit ports reselects a deterministic pair
        # when the default endpoints are occupied by another task.
        launch_command = (
            _select_automatic_ports(lifecycle, launch_base, selected_home)
            if automatic_ports
            else launch_base
        )
        http_port = _validated_http_port(launch_command)
    except ValueError as error:
        progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(f"Invalid service port: {error}")
        )
        fallback_ports = None
        try:
            fallback_ports = service_ports_from_command(command)
        except ValueError:
            pass
        _print_lifecycle_result(
            "restart",
            selected_home,
            result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
            before_projection=before_projection,
            command=command,
            fallback_ports=fallback_ports,
        )
        return result
    attempted_ports: list[tuple[int, int]] = []
    supervisor = _supervisor_for(
        lifecycle,
        launch_command,
        http_port,
        selected_home=selected_home,
        automatic_ports=automatic_ports,
    )
    result = supervisor.start(owner_id="cli")
    while (
        result.status == "failed"
        and automatic_ports
        and _is_automatic_port_conflict(result)
        and len(attempted_ports) < 2
    ):
        attempted_ports.append(service_ports_from_command(launch_command))
        retry_command = _select_automatic_ports(
            lifecycle,
            launch_base,
            selected_home,
            avoid_pairs=attempted_ports,
        )
        if retry_command == launch_base:
            break
        launch_command = retry_command
        http_port = _validated_http_port(launch_command)
        supervisor = _supervisor_for(
            lifecycle,
            launch_command,
            http_port,
            selected_home=selected_home,
            automatic_ports=automatic_ports,
        )
        result = supervisor.start(owner_id="cli")
    succeeded = result.status in {"started", "already_running"}
    progress.stop(success=succeeded, clear_only=True)
    _print_lifecycle_result(
        "restart",
        selected_home,
        result,
        projection=_safe_runtime_projection(lifecycle, selected_home),
        before_projection=before_projection,
        command=launch_command,
        fallback_ports=service_ports_from_command(launch_command),
    )

    # Enhanced error message for port occupation
    if not succeeded and isinstance(result.error, ServicePortsActiveError):
        print()
        occupied = _diagnose_ports_for_command(
            lifecycle,
            launch_command,
            selected_home=selected_home,
        )
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
                "  💡 Stop the exact task owning these ports, or start with an unused explicit port pair"
            )

    return result


def show_service_status(
    lifecycle: LifecycleFacade,
    *,
    json_output: bool = False,
    selected_home: Path | None = None,
) -> None:
    """Print only the selected root's authoritative Runtime snapshot."""
    elfie_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        selected_home=selected_home,
    )
    health = lifecycle.runtime_projection(elfie_home)
    if json_output:
        _print_runtime_health_json(health, data_root=elfie_home)
        return
    print("  📊 Service Status")
    print("  " + "=" * 45)
    print()
    print(f"  Data root: {elfie_home}")
    print(f"  Instance: {health.instance_id}")
    print(f"  Runtime: {health.tier.value} ({health.phase.value})")
    print(f"  Generation: {health.generation}")
    published_ports = _published_service_ports(health)
    port_statuses = (
        lifecycle.service_port_statuses(*published_ports)
        if published_ports is not None
        else ()
    )
    for port_status in port_statuses:
        state = "running" if port_status.running else "not running"
        icon = "✅" if port_status.running else "⭕"
        print(f"  {icon} {port_status.name}: {state} (port {port_status.port})")
    for endpoint in health.endpoints:
        print(f"  {_endpoint_label(endpoint)} address: {_endpoint_address(endpoint)}")
    if not port_statuses:
        print("  ⭕ No endpoint is published by this Runtime snapshot")
    if health.components:
        print()
        for component in health.components:
            print(f"  - {component.component.value}: {component.state.value}")
            if component.pid is not None:
                print(f"    PID: {component.pid}")
        print(
            "  Model: "
            f"{health.model_state.value} "
            f"(common={health.model_common_state.value}, "
            f"emergency={health.model_emergency_state.value})"
        )
    print()


def open_web_console(
    lifecycle: LifecycleFacade,
    *,
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Open the selected task's published endpoint without starting Runtime."""
    selected_home = selected_runtime_data_home(
        lifecycle,
        selected_home=selected_home,
    )
    snapshot = lifecycle.runtime_snapshot(selected_home)
    if snapshot.tier is BackendTier.OFFLINE:
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(
                "Selected Runtime is offline; web only opens an existing service "
                f"(data_root={selected_home}). Run start first."
            ),
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="web",
            result=result,
            projection=snapshot.projection(),
        )
        print(f"  ❌ Cannot open Web console: {result.error}")
        return result
    port = published_http_port_for_home(lifecycle, selected_home)
    if port is None:
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(
                "Selected Runtime did not publish an HTTP endpoint "
                f"(data_root={selected_home}, generation={snapshot.generation})"
            ),
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="web",
            result=result,
            projection=snapshot.projection(),
        )
        print(f"  ❌ Cannot open Web console: {result.error}")
        return result
    if not _web_is_healthy(
        lifecycle,
        port,
        expected_identity=(snapshot.instance_id, snapshot.generation),
    ):
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(
                f"Selected Runtime endpoint failed health check: {selected_home}:{port}"
            ),
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="web",
            result=result,
            projection=snapshot.projection(),
            fallback_ports=(port, DEFAULT_GODOT_WS_PORT),
        )
        print(f"  ❌ Cannot open Web console: {result.error}")
        return result
    web_url = f"http://127.0.0.1:{port}/"
    result = ServiceLifecycleResult(
        status="already_running", command=("--port", str(port))
    )
    _print_operation_context(
        lifecycle,
        selected_home,
        action="web",
        result=result,
        projection=snapshot.projection(),
    )
    webbrowser.open(web_url)
    print(f"  🌐 Opened Web console: {web_url}")
    return result


def open_desktop_application(
    lifecycle: LifecycleFacade,
    *,
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Activate an existing Desktop Viewer without starting Controller/Runtime."""
    selected_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(),
        selected_home=selected_home,
    )
    snapshot = _safe_runtime_projection(lifecycle, selected_home)
    http_port = published_http_port_for_home(lifecycle, selected_home)
    if (
        snapshot is None
        or snapshot.tier is BackendTier.OFFLINE
        or http_port is None
        or not _web_is_healthy(
            lifecycle,
            http_port,
            expected_identity=(snapshot.instance_id, snapshot.generation)
            if snapshot is not None
            else None,
        )
    ):
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(
                "Selected Runtime is not running with a healthy HTTP endpoint; "
                "desktop only opens an existing Viewer and never starts the service "
                f"(data_root={selected_home})."
            ),
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="desktop",
            result=result,
            projection=snapshot,
        )
        print(f"  ❌ Cannot open Desktop Viewer: {result.error}")
        return result
    try:
        controller_result = lifecycle.controller_request(
            "ACTIVATE_VIEWER", expected_data_home=selected_home
        )
    except RuntimeError as error:
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Controller activation rejected: {error}"),
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="desktop",
            result=result,
            projection=snapshot,
        )
        print(f"  ❌ Cannot open Desktop Viewer: {result.error}")
        return result
    if controller_result is None:
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(
                "Desktop Controller is not running; desktop only opens an existing "
                "Viewer and will not start the service."
            ),
        )
        _print_operation_context(
            lifecycle,
            selected_home,
            action="desktop",
            result=result,
            projection=snapshot,
        )
        print(f"  ❌ Cannot open Desktop Viewer: {result.error}")
        return result
    failure = _controller_failure_result(controller_result, "activate Viewer")
    if failure is not None:
        _print_operation_context(
            lifecycle,
            selected_home,
            action="desktop",
            result=failure,
            projection=snapshot,
        )
        print(f"  ❌ Cannot open Desktop Viewer: {failure.error}")
        return failure
    _print_operation_context(
        lifecycle,
        selected_home,
        action="desktop",
        result=ServiceLifecycleResult(status="already_running"),
        projection=snapshot,
    )
    print("  ✅ Desktop Viewer activated")
    return ServiceLifecycleResult(status="already_running")


def _should_start_packaged_controller() -> bool:
    """Installed CLI owns a tray Controller; its internal calls do not."""
    return (
        bool(getattr(sys, "frozen", False))
        and os.environ.get("ELFIENEST_CONTROLLER_CLIENT") != "1"
    )


def _start_packaged_controller(
    lifecycle: LifecycleFacade,
    *,
    command: Optional[Sequence[str]] = None,
    json_output: bool,
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Ensure the installed Controller without opening its Viewer."""
    selected_home = _data_home_for_command(
        lifecycle,
        lifecycle.default_service_command(("--lan",)),
        selected_home=selected_home,
    )
    if command is not None and _option_value(command, "--data-home") is not None:
        result = ServiceLifecycleResult(
            status="failed",
            command=tuple(command),
            error=LaunchFailedError(
                "Installed elfienest start does not support --data-home; "
                "use ${ELFIE_HOME:-~/.elfienest}, or use the source CLI for "
                "an isolated development instance"
            ),
        )
        if json_output:
            _print_start_result_or_json(
                lifecycle,
                result,
                json_output=True,
                selected_home=selected_home,
                action="start",
            )
        else:
            _print_operation_context(
                lifecycle,
                selected_home,
                action="start",
                result=result,
                projection=_safe_runtime_projection(lifecycle, selected_home),
            )
            print(f"  ❌ Controller failed to start: {result.error}")
        return result
    try:
        controller_result = lifecycle.controller_request(
            "ENSURE_SERVER", expected_data_home=selected_home
        )
    except RuntimeError as error:
        result = ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Controller start rejected: {error}"),
        )
        if json_output:
            _print_start_result_or_json(
                lifecycle,
                result,
                json_output=True,
                selected_home=selected_home,
                action="start",
            )
        else:
            _print_operation_context(
                lifecycle,
                selected_home,
                action="start",
                result=result,
                projection=_safe_runtime_projection(lifecycle, selected_home),
            )
            print(f"  ❌ Controller failed to start: {result.error}")
        return result
    if controller_result is not None:
        failure = _controller_failure_result(controller_result, "start")
        if failure is not None:
            if json_output:
                _print_start_result_or_json(
                    lifecycle,
                    failure,
                    json_output=True,
                    selected_home=selected_home,
                    action="start",
                )
            else:
                _print_operation_context(
                    lifecycle,
                    selected_home,
                    action="start",
                    result=failure,
                    projection=_safe_runtime_projection(lifecycle, selected_home),
                )
                print(f"  ❌ Controller failed to start: {failure.error}")
            return failure
        if json_output:
            _print_runtime_health_json(
                lifecycle.runtime_projection(selected_home),
                data_root=selected_home,
            )
        else:
            _print_operation_context(
                lifecycle,
                selected_home,
                action="start",
                result=ServiceLifecycleResult(status="already_running"),
                projection=_safe_runtime_projection(lifecycle, selected_home),
            )
            print("  ⭕ Controller already running; Viewer remains closed")
            _print_web_console_link_for_home(lifecycle, selected_home)
        return ServiceLifecycleResult(status="already_running")

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
                lifecycle.runtime_snapshot(selected_home).projection(),
                data_root=selected_home,
            )
        else:
            _print_start_result_or_json(
                lifecycle,
                result,
                json_output=True,
                selected_home=selected_home,
                action="start",
            )
    elif result.status == "started":
        _print_operation_context(
            lifecycle,
            selected_home,
            action="start",
            result=result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
        )
        print(f"  ✅ Controller started (PID {result.pid}); Viewer remains closed")
        _print_web_console_link_for_home(lifecycle, selected_home)
    elif result.status == "already_running":
        _print_operation_context(
            lifecycle,
            selected_home,
            action="start",
            result=result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
        )
        print(f"  ⭕ Controller already running (PID {result.pid})")
        _print_web_console_link_for_home(lifecycle, selected_home)
    else:
        _print_operation_context(
            lifecycle,
            selected_home,
            action="start",
            result=result,
            projection=_safe_runtime_projection(lifecycle, selected_home),
        )
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


def _web_is_healthy(
    lifecycle: LifecycleFacade,
    port: int,
    *,
    expected_identity: tuple[str, int] | None = None,
) -> bool:
    health_url = f"http://127.0.0.1:{port}/api/health"
    try:
        response = lifecycle.http_get(health_url, timeout_seconds=2.0)
        if response.status != 200:
            return False
        payload = json.loads(response.body.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            return False
        if expected_identity is None:
            return True
        instance_id, generation = expected_identity
        return (
            payload.get("instance_id") == instance_id
            and payload.get("generation") == generation
        )
    except (OSError, TimeoutError, UnicodeDecodeError, ValueError, TypeError):
        return False


def _diagnose_ports_for_command(
    lifecycle: LifecycleFacade,
    command: Sequence[str],
    *,
    selected_home: Path | None = None,
    projection: RuntimeProjectionV1 | None = None,
) -> dict[int, ProcessInfo]:
    """Inspect only the endpoint pair belonging to the failed task.

    A restart/stop command may not repeat the ports chosen by the previous
    generation.  In that case the selected data root's live projection is the
    authority; explicit ports on the command still win because they describe
    the endpoint currently being attempted.
    """
    from app.interfaces.cli.doctor_commands import diagnose_ports

    explicit_ports = _has_port_option(command, "--port") or _has_port_option(
        command, "--godot-ws-port"
    )
    ports: tuple[int, int] | tuple[int, ...] | None = None
    if not explicit_ports:
        if projection is not None:
            ports = _published_service_ports(projection)
        elif selected_home is not None:
            try:
                ports = _published_service_ports(
                    lifecycle.runtime_projection(selected_home)
                )
            except (AttributeError, OSError, RuntimeError, ValueError):
                ports = None
    if ports is None:
        try:
            ports = service_ports_from_command(command)
        except (TypeError, ValueError):
            ports = (DEFAULT_HTTP_PORT, DEFAULT_GODOT_WS_PORT)
    return diagnose_ports(lifecycle=lifecycle, ports=tuple(dict.fromkeys(ports)))


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


def published_http_port_for_home(
    lifecycle: LifecycleFacade, selected_home: Path
) -> int | None:
    """Read the current HTTP endpoint from the lifecycle-owned snapshot."""
    try:
        snapshot = lifecycle.runtime_snapshot(selected_home)
    except (OSError, RuntimeError, ValueError):
        return None
    if snapshot.tier is BackendTier.OFFLINE:
        return None
    projection = snapshot.projection()
    for endpoint in projection.endpoints:
        if endpoint.name == "http" and 1 <= endpoint.port <= 65535:
            return endpoint.port
    return None


def _validated_http_port(command: Sequence[str]) -> int:
    """Parse and validate HTTP/Godot ports before spawning a service process."""
    ports = service_ports_from_command(command)
    error = validate_service_ports(ports[0], ports[1])
    if error:
        raise ValueError(error)
    return ports[0]


def _web_console_url(
    result: ServiceLifecycleResult,
    supervisor: RuntimeLifecycle | None = None,
    projection: RuntimeProjectionV1 | None = None,
) -> str | None:
    """Return the loopback Web URL from the published Runtime endpoint."""
    port: int | None = None
    if result.command is not None:
        if _has_port_option(result.command, "--port"):
            port = http_port_from_command(result.command)
    if port is None:
        published_ports = _published_service_ports(projection) if projection else None
        if published_ports is None and supervisor is not None:
            try:
                published_ports = _published_service_ports(supervisor.status())
            except (OSError, RuntimeError, ValueError):
                published_ports = None
        port = published_ports[0] if published_ports is not None else None
    if port is None:
        return None
    return f"http://127.0.0.1:{port}/"


def _safe_runtime_projection(
    lifecycle: LifecycleFacade, selected_home: Path
) -> RuntimeProjectionV1 | None:
    """Read the selected root's projection without hiding command failures."""
    try:
        projection = lifecycle.runtime_projection(selected_home)
        if isinstance(projection, RuntimeProjectionV1):
            return projection
        return None
    except (AttributeError, OSError, RuntimeError, ValueError):
        # Diagnostics must not consume a one-shot runtime observation or turn
        # a command's authoritative stop/wait sequence into a second read.
        return None


def _endpoint_label(endpoint: EndpointSnapshot) -> str:
    if endpoint.name == "http":
        return "HTTP"
    if endpoint.name == "godot_ws":
        return "Godot WebSocket"
    return endpoint.name


def _endpoint_address(endpoint: EndpointSnapshot) -> str:
    host = endpoint.host
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    suffix = "/" if endpoint.scheme in {"http", "https"} else ""
    return f"{endpoint.scheme}://{host}:{endpoint.port}{suffix}"


@contextmanager
def display_data_home(value: Optional[str]) -> Iterator[None]:
    """Scope the non-authoritative spelling used by compact CLI output."""
    token = _DISPLAY_DATA_HOME.set(value)
    try:
        yield
    finally:
        _DISPLAY_DATA_HOME.reset(token)


def _display_data_home(selected_home: Path) -> str:
    """Use the user's selected spelling without changing the canonical target."""
    selected = _DISPLAY_DATA_HOME.get()
    if selected:
        return selected
    canonical = selected_home.resolve(strict=False)
    for base, prefix in (
        (Path.cwd().resolve(), ""),
        (Path.home().resolve(), "~/"),
    ):
        try:
            relative = canonical.relative_to(base)
        except ValueError:
            continue
        relative_text = str(relative)
        return f"{prefix}{relative_text}" if relative_text != "." else (prefix or ".")
    return str(canonical)


def _lifecycle_identity_text(
    selected_home: Path,
    *,
    result: ServiceLifecycleResult | None = None,
    projection: RuntimeProjectionV1 | None = None,
    command: Sequence[str] = (),
    fallback_ports: tuple[int, int] | None = None,
) -> str:
    """Render the compact identity used before and after a source lifecycle call."""
    generation = (
        projection.generation
        if projection is not None and projection.generation > 0
        else result.generation
        if result is not None and result.generation is not None
        else None
    )
    core_pid = (
        result.pid
        if result is not None and result.pid is not None
        else projection.component(RuntimeComponent.CORE).pid
        if projection is not None
        else None
    )
    ports = _published_service_ports(projection) if projection is not None else None
    if ports is None:
        ports = fallback_ports
    if ports is None and command:
        try:
            ports = service_ports_from_command(command)
        except ValueError:
            ports = None

    parts = [f"data: {_display_data_home(selected_home)}"]
    if generation is not None and generation > 0:
        parts.append(f"generation: {generation}")
    parts.append(f"PID: {core_pid if core_pid is not None else 'pending'}")
    if ports is None:
        parts.extend(("HTTP: pending", "WS: pending"))
    else:
        parts.extend((f"HTTP: {ports[0]}", f"WS: {ports[1]}"))
    return " · ".join(parts)


def _print_lifecycle_intent(
    action: str,
    selected_home: Path,
    *,
    projection: RuntimeProjectionV1 | None = None,
    command: Sequence[str] = (),
    fallback_ports: tuple[int, int] | None = None,
) -> None:
    """Print one compact target line before a source lifecycle operation."""
    labels = {
        "start": "Starting service",
        "serve": "Starting foreground service",
        "restart": "Restarting service",
        "stop": "Stopping service",
    }
    label = labels.get(action, f"Running {action}")
    print(
        f"  ⏳ {label} ("
        f"{_lifecycle_identity_text(selected_home, projection=projection, command=command, fallback_ports=fallback_ports)}"
        ")"
    )


def _print_lifecycle_result(
    action: str,
    selected_home: Path,
    result: ServiceLifecycleResult,
    *,
    projection: RuntimeProjectionV1 | None = None,
    before_projection: RuntimeProjectionV1 | None = None,
    command: Sequence[str] = (),
    fallback_ports: tuple[int, int] | None = None,
) -> None:
    """Print one compact final line for a source lifecycle operation."""
    identity_projection = (
        before_projection
        if action == "stop" and before_projection is not None
        else projection
    )
    identity = _lifecycle_identity_text(
        selected_home,
        result=result,
        projection=identity_projection,
        command=command,
        fallback_ports=fallback_ports,
    )
    if result.status == "started":
        if action == "serve":
            label = "Foreground service started"
        elif action == "restart":
            label = "Service restarted"
        else:
            label = "Service started"
        print(f"  ✅ {label} ({identity})")
    elif result.status == "already_running":
        print(f"  ⭕ Service already running ({identity})")
    elif result.status == "stopped":
        print(f"  ✅ Service stopped ({identity})")
    elif result.status == "already_stopped":
        print(f"  ⭕ Service already stopped ({identity})")
    else:
        labels = {
            "start": "Service start failed",
            "serve": "Foreground service start failed",
            "restart": "Service restart failed",
            "stop": "Service stop failed",
        }
        label = labels.get(action, f"{action} failed")
        print(f"  ❌ {label} ({identity}): {result.error}")
        return

    if action in {"start", "serve", "restart"} and result.status in {
        "started",
        "already_running",
    }:
        web_url = _web_console_url(result, projection=identity_projection)
        if web_url is not None:
            print(f"  🌐 Web console: {web_url}")


def _print_operation_context(
    lifecycle: LifecycleFacade,
    selected_home: Path,
    *,
    action: str,
    result: ServiceLifecycleResult | None = None,
    projection: RuntimeProjectionV1 | None = None,
    fallback_ports: tuple[int, int] | None = None,
) -> None:
    """Print only the target, component PIDs and published endpoint pair."""
    print(f"  🔧 {action} (data: {_display_data_home(selected_home)})")

    component_pids = []
    if projection is not None:
        labels = {
            RuntimeComponent.CORE: "core",
            RuntimeComponent.GATEWAY: "gateway",
            RuntimeComponent.GODOT_AUTHORITY: "godot",
        }
        for component, label in labels.items():
            pid = projection.component(component).pid
            if pid is not None:
                component_pids.append(f"{label}={pid}")
    if not component_pids and result is not None and result.pid is not None:
        component_pids.append(f"core={result.pid}")
    if component_pids:
        print(f"  PID: {' · '.join(component_pids)}")

    ports = _published_service_ports(projection) if projection is not None else None
    if ports is None:
        ports = fallback_ports
    if ports is not None:
        print(f"  Ports: HTTP={ports[0]} · WS={ports[1]}")


def _print_web_console_link_for_home(
    lifecycle: LifecycleFacade, selected_home: Path
) -> None:
    try:
        projection = lifecycle.runtime_snapshot(selected_home).projection()
    except (OSError, RuntimeError, ValueError):
        projection = None
    web_url = _web_console_url(
        ServiceLifecycleResult(status="started"), projection=projection
    )
    if web_url is not None:
        print(f"  🌐 Web console: {web_url}")


def _print_start_result(
    lifecycle: LifecycleFacade,
    result: ServiceLifecycleResult,
    *,
    supervisor: RuntimeLifecycle | None = None,
    selected_home: Path | None = None,
    action: str = "start",
    compact: bool = False,
) -> None:
    selected_home = selected_home or _data_home_for_command(
        lifecycle,
        result.command or lifecycle.default_service_command(),
    )
    projection = None
    if supervisor is not None:
        try:
            projection = supervisor.status()
        except (OSError, RuntimeError, ValueError):
            projection = None
    if projection is None:
        projection = _safe_runtime_projection(lifecycle, selected_home)

    published_ports = _published_service_ports(projection) if projection else None
    if published_ports is None and result.command is not None:
        try:
            published_ports = service_ports_from_command(result.command)
        except ValueError:
            published_ports = None

    if compact:
        _print_lifecycle_result(
            action,
            selected_home,
            result,
            projection=projection,
            command=result.command or (),
            fallback_ports=published_ports,
        )
        return

    _print_operation_context(
        lifecycle,
        selected_home,
        action=action,
        result=result,
        projection=projection,
        fallback_ports=published_ports,
    )

    if result.status == "started":
        pid = result.pid or (
            projection.component(RuntimeComponent.CORE).pid
            if projection is not None
            else None
        )
        print(f"  ✅ Service started (PID {pid})")
        web_url = _web_console_url(result, projection=projection)
        if web_url is not None:
            print(f"  🌐 Web console: {web_url}")
    elif result.status == "already_running":
        pid = result.pid or (
            projection.component(RuntimeComponent.CORE).pid
            if projection is not None
            else None
        )
        print(f"  ⭕ Service already running (PID {pid})")
        web_url = _web_console_url(result, projection=projection)
        if web_url is not None:
            print(f"  🌐 Web console: {web_url}")
    else:
        print(f"  ❌ Service failed to start: {result.error}")

        # Enhanced error message for port occupation
        if isinstance(result.error, ServicePortsActiveError):
            print()
            occupied = _diagnose_ports_for_command(
                lifecycle,
                result.command or lifecycle.default_service_command(),
                selected_home=selected_home,
            )
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
                    "  💡 Stop the exact task owning these ports, or start with an unused explicit port pair"
                )
            else:
                print(
                    "  ℹ️  Service ports appear free but were occupied during startup."
                )
                print("     This might indicate a race condition or transient issue.")


def _runtime_health_payload(
    health: RuntimeProjectionV1,
    *,
    data_root: Path | None = None,
) -> dict[str, object]:
    """Serialize the one lifecycle projection for machine clients."""
    payload: dict[str, object] = {
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
                "executable": component.executable,
                "birth_identity": component.birth_identity,
                "cwd": component.cwd,
            }
            for component in health.components
        ],
    }
    if data_root is not None:
        payload["data_root"] = str(data_root)
    return payload


def _print_runtime_health_json(
    health: RuntimeProjectionV1,
    *,
    data_root: Path | None = None,
) -> None:
    print(
        json.dumps(
            _runtime_health_payload(health, data_root=data_root),
            ensure_ascii=False,
            sort_keys=True,
        )
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
    selected_home: Path | None = None,
    action: str = "start",
    compact: bool = False,
) -> None:
    """Render either the selected human panel or one machine-readable result."""
    selected_home = selected_home or _data_home_for_command(
        lifecycle,
        result.command or lifecycle.default_service_command(),
    )
    if not json_output:
        _print_start_result(
            lifecycle,
            result,
            supervisor=supervisor,
            selected_home=selected_home,
            action=action,
            compact=compact,
        )
        return
    if result.status in {"started", "already_running"} and supervisor is not None:
        _print_runtime_health_json(
            supervisor.status(),
            data_root=selected_home,
        )
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
                "data_root": str(selected_home),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
