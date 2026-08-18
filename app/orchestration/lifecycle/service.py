"""Safe lifecycle management for the local ElfieNest service."""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from app.orchestration.lifecycle.commands import (
    MANAGED_START_ENV,
    command_matches_service,
    restart_command_from_process,
    service_ports_from_command,
)
from app.orchestration.lifecycle.helpers import (
    existing_service_command,
    recorded_pid,
)
from app.orchestration.lifecycle.ports import (
    RecoveryLockPort,
    RuntimeRecordPort,
    ServiceProcessPort,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    RuntimeComponent,
    RuntimePhase,
)
from app.orchestration.lifecycle.start_cleanup import cleanup_failed_start
from app.orchestration.lifecycle.types import (
    HealthCheckFailedError,
    InvalidPidFileError,
    LaunchFailedError,
    ProcessIdentityMismatchError,
    ProcessIdentityUnavailableError,
    ProcessInspectionError,
    RecoveryInProgressError,
    ServiceLifecycleResult,
    ServicePortsActiveError,
    SignalProcessError,
    StopTimeoutError,
)

SERVICE_STOP_GRACE_SECONDS = 2.0
SERVICE_STOP_FORCE_GRACE_SECONDS = 2.0


def stop_service(
    elfie_home: Path,
    project_root: Path,
    *,
    process_port: ServiceProcessPort,
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.1,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    expected_command: Sequence[str] = (),
    runtime_record: Optional[RuntimeRecordPort] = None,
) -> ServiceLifecycleResult:
    """Stop the exact generation recorded by the selected data root."""
    if runtime_record is None:
        return ServiceLifecycleResult(
            status="failed",
            error=ProcessIdentityUnavailableError(
                0,
                "Runtime snapshot is required; refusing to control a PID receipt without a selected generation",
            ),
        )
    return _stop_snapshot_bound_service(
        elfie_home,
        project_root,
        process_port=process_port,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        monotonic=monotonic,
        sleeper=sleeper,
        expected_command=expected_command,
        runtime_record=runtime_record,
    )


def _stop_snapshot_bound_service(
    elfie_home: Path,
    project_root: Path,
    *,
    process_port: ServiceProcessPort,
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
    expected_command: Sequence[str],
    runtime_record: RuntimeRecordPort,
) -> ServiceLifecycleResult:
    """Validate generation, birth identity and executable before every signal."""
    try:
        snapshot = runtime_record.read()
    except (OSError, RuntimeError, ValueError) as error:
        return ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Runtime snapshot unavailable: {error}"),
        )

    endpoint_ports = _runtime_ports(runtime_record)
    if snapshot.tier is BackendTier.OFFLINE and snapshot.phase in {
        RuntimePhase.OFFLINE,
        RuntimePhase.RECOVERY_REQUIRED,
    }:
        if endpoint_ports and process_port.ports_in_use(endpoint_ports):
            return ServiceLifecycleResult(
                status="failed",
                error=ServicePortsActiveError(
                    "Runtime snapshot is OFFLINE but its recorded endpoint is occupied; "
                    "the occupant was not terminated"
                ),
            )
        if process_port.receipt_exists(elfie_home):
            process_port.clear_receipt(elfie_home)
        return ServiceLifecycleResult(status="already_stopped")

    component = snapshot.component(RuntimeComponent.CORE)
    pid = component.pid
    if pid is None:
        return ServiceLifecycleResult(
            status="failed",
            error=ProcessIdentityUnavailableError(
                0,
                "current Runtime generation has no Core PID; refusing to use a receipt or port",
            ),
        )
    if not component.birth_identity or not component.executable or not component.cwd:
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=ProcessIdentityUnavailableError(
                pid,
                "current Runtime generation lacks birth identity, executable or cwd",
            ),
        )

    if process_port.receipt_exists(elfie_home):
        try:
            receipt_pid = recorded_pid(elfie_home, process_port)
        except OSError as error:
            return ServiceLifecycleResult(
                status="failed",
                pid=pid,
                error=InvalidPidFileError(elfie_home / "elfienest.pid", str(error)),
            )
        if isinstance(receipt_pid, InvalidPidFileError):
            return ServiceLifecycleResult(status="failed", pid=pid, error=receipt_pid)
        if receipt_pid is not None and receipt_pid != pid:
            return ServiceLifecycleResult(
                status="failed",
                pid=pid,
                error=ProcessIdentityUnavailableError(
                    pid,
                    f"receipt PID {receipt_pid} does not belong to generation {snapshot.generation}",
                ),
            )

    if not process_port.exists(pid):
        if endpoint_ports and process_port.ports_in_use(endpoint_ports):
            ownership = _owned_endpoint_state(
                endpoint_ports,
                process_port=process_port,
                component=component,
                project_root=project_root,
                expected_command=expected_command,
            )
            if ownership is not False:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=ServicePortsActiveError(
                        "Recorded Core PID is gone but a recorded endpoint is still "
                        "owned by this generation or its owner cannot be verified"
                    ),
                )
        process_port.clear_receipt(elfie_home)
        return ServiceLifecycleResult(status="already_stopped", pid=pid)

    try:
        observed = process_port.inspect(pid)
    except (OSError, RuntimeError, ValueError) as error:
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=ProcessInspectionError(pid, str(error))
        )
    mismatch = _snapshot_identity_mismatch(
        observed,
        component,
        project_root=project_root,
        expected_command=expected_command,
    )
    if mismatch is not None:
        return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)

    # The first inspection only proves the PID at the beginning of the stop
    # decision.  Inspect again immediately before signalling so a fast
    # exit/reuse cannot turn a stale snapshot into a kill of another process.
    try:
        latest = process_port.inspect(pid)
    except (OSError, RuntimeError, ValueError) as error:
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=ProcessInspectionError(pid, str(error))
        )
    mismatch = _snapshot_identity_mismatch(
        latest,
        component,
        project_root=project_root,
        expected_command=expected_command,
    )
    if mismatch is not None:
        return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)
    observed = latest

    try:
        process_port.terminate(pid)
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", pid=pid, error=SignalProcessError(pid, str(error))
        )
    deadline = monotonic() + timeout_seconds
    graceful_deadline = min(deadline, monotonic() + SERVICE_STOP_GRACE_SECONDS)
    forced = False
    while process_port.exists(pid):
        now = monotonic()
        if now >= graceful_deadline and not forced:
            try:
                recheck = process_port.inspect(pid)
            except (OSError, RuntimeError, ValueError) as error:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=ProcessInspectionError(pid, str(error)),
                )
            mismatch = _snapshot_identity_mismatch(
                recheck,
                component,
                project_root=project_root,
                expected_command=expected_command,
            )
            if mismatch is not None:
                return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)
            if now >= deadline:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=StopTimeoutError(pid, timeout_seconds),
                )
            try:
                process_port.terminate(pid, force=True)
            except OSError as error:
                return ServiceLifecycleResult(
                    status="failed", pid=pid, error=SignalProcessError(pid, str(error))
                )
            forced = True
        if monotonic() >= deadline:
            return ServiceLifecycleResult(
                status="failed", pid=pid, error=StopTimeoutError(pid, timeout_seconds)
            )
        sleeper(poll_interval_seconds)

    if endpoint_ports and process_port.ports_in_use(endpoint_ports):
        ownership = _owned_endpoint_state(
            endpoint_ports,
            process_port=process_port,
            component=component,
            project_root=project_root,
            expected_command=expected_command,
        )
        if ownership is not False:
            return ServiceLifecycleResult(
                status="failed",
                pid=pid,
                error=ServicePortsActiveError(
                    "Core exited but a recorded endpoint is still owned by this "
                    "generation or its owner cannot be verified"
                ),
            )
    process_port.remove_receipt(elfie_home, pid)
    return ServiceLifecycleResult(
        status="stopped",
        pid=pid,
        command=restart_command_from_process(observed.command),
    )


def _snapshot_identity_mismatch(
    observed,
    component,
    *,
    project_root: Path,
    expected_command: Sequence[str],
) -> ProcessIdentityMismatchError | ProcessIdentityUnavailableError | None:
    if not observed.birth_identity:
        return ProcessIdentityUnavailableError(
            observed.pid,
            "observed process birth identity is unavailable",
        )
    if observed.birth_identity != component.birth_identity:
        return ProcessIdentityMismatchError(
            observed.pid,
            Path(component.cwd),
            observed.cwd.resolve(),
            (
                Path(component.executable)
                if component.executable
                else project_root / "scripts" / "serve.py"
            ),
            observed.command,
        )
    if observed.cwd.resolve() != Path(component.cwd).resolve():
        return ProcessIdentityMismatchError(
            observed.pid,
            Path(component.cwd),
            observed.cwd.resolve(),
            Path(component.executable),
            observed.command,
        )
    expected_executable = Path(component.executable).resolve()
    actual_executable = _observed_executable(
        observed.command,
        expected_executable,
    )
    if actual_executable is None or actual_executable.resolve() != expected_executable:
        return ProcessIdentityMismatchError(
            observed.pid,
            Path(component.cwd),
            observed.cwd.resolve(),
            expected_executable,
            observed.command,
        )
    expected_script = Path(component.cwd).resolve() / "scripts" / "serve.py"
    if expected_command and not command_matches_service(
        observed.command,
        observed.cwd.resolve(),
        expected_script,
        expected_command,
    ):
        return ProcessIdentityMismatchError(
            observed.pid,
            Path(component.cwd),
            observed.cwd.resolve(),
            expected_script,
            observed.command,
        )
    return None


def _owned_endpoint_state(
    endpoint_ports: Sequence[int],
    *,
    process_port: ServiceProcessPort,
    component,
    project_root: Path,
    expected_command: Sequence[str],
) -> Optional[bool]:
    """Classify occupied endpoints without granting port-based stop authority.

    ``True`` means an occupant was re-verified as the recorded Core generation;
    ``False`` means every observed occupant is external; ``None`` means the
    platform could not provide enough evidence to decide.  An external occupant
    is never signalled and does not keep an already-dead generation online.
    """
    if component.pid is None:
        return False
    unverifiable = False
    for port in endpoint_ports:
        try:
            occupant_pid = process_port.port_occupant_pid(port)
        except (OSError, RuntimeError, ValueError):
            unverifiable = True
            continue
        if occupant_pid is None or occupant_pid != component.pid:
            continue
        try:
            observed = process_port.inspect(occupant_pid)
        except (OSError, RuntimeError, ValueError):
            unverifiable = True
            continue
        if (
            _snapshot_identity_mismatch(
                observed,
                component,
                project_root=project_root,
                expected_command=expected_command,
            )
            is None
        ):
            return True
    if unverifiable:
        return None
    return False


def _observed_executable(
    command: Sequence[str], expected: Path | None = None
) -> Path | None:
    if not command:
        return None
    if expected is not None:
        for count in range(1, len(command) + 1):
            candidate = Path(" ".join(command[:count]))
            if candidate.resolve(strict=False) == expected:
                return candidate
    return Path(command[0])


def _runtime_ports(runtime_record: Optional[RuntimeRecordPort]) -> tuple[int, ...]:
    """Use published endpoints when a dynamic service has no PID receipt."""
    if runtime_record is None:
        return ()
    try:
        snapshot = runtime_record.read()
    except (OSError, RuntimeError, ValueError):
        return ()
    ports = tuple(
        endpoint.port
        for endpoint in snapshot.endpoints
        if endpoint.name in {"http", "godot_ws"} and endpoint.port > 0
    )
    return tuple(dict.fromkeys(ports))


def detail_path_for_home(elfie_home: Path) -> Path:
    """Return the canonical per-task managed service log path."""
    return (elfie_home / "logs" / "service.log").resolve()


def start_service(
    elfie_home: Path,
    project_root: Path,
    *,
    process_port: ServiceProcessPort,
    recovery_lock: RecoveryLockPort,
    health_checker: Callable[[], bool],
    command: Optional[Sequence[str]] = None,
    timeout_seconds: float = 10.0,
    poll_interval_seconds: float = 0.1,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    child_environment: Optional[Mapping[str, str]] = None,
    runtime_record: Optional[RuntimeRecordPort] = None,
) -> ServiceLifecycleResult:
    """Start the service; terminate it and remove the PID file when health fails."""
    resolved_root = project_root.resolve()
    launch_command = (
        tuple(command)
        if command is not None
        else (
            sys.executable,
            str((resolved_root / "scripts" / "serve.py").resolve()),
        )
    )
    automatic_ports = (
        child_environment is not None
        and child_environment.get("ELFIENEST_PORT_MODE") == "automatic"
    )
    try:
        startup_lease = recovery_lock.acquire_start_lease(elfie_home)
    except (OSError, RecoveryInProgressError) as error:
        return ServiceLifecycleResult(
            status="failed",
            error=LaunchFailedError(f"Service startup blocked: {error}"),
        )
    lease_released = False
    try:
        existing = existing_service_command(
            elfie_home,
            resolved_root,
            process_port,
            runtime_record=runtime_record,
            expected_command=launch_command,
        )
        if existing is not None:
            existing_pid, existing_command = existing
            requested_ports = service_ports_from_command(launch_command)
            existing_ports = service_ports_from_command(existing_command)
            if not automatic_ports and requested_ports != existing_ports:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=existing_pid,
                    error=LaunchFailedError(
                        "An existing service is using different ports; run restart or stop before changing ports"
                    ),
                )
            # The command reservation only protects the short read/decision
            # window.  Never hold it while waiting on an HTTP health probe.
            startup_lease.release()
            lease_released = True
            health_error: Exception | None = None
            try:
                existing_healthy = health_checker()
            except (OSError, RuntimeError, ValueError) as error:
                health_error = error
                existing_healthy = False
            if not existing_healthy:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=existing_pid,
                    command=existing_command,
                    error=HealthCheckFailedError(
                        existing_pid,
                        0.0,
                        detail_path_for_home(elfie_home),
                        str(health_error) if health_error is not None else None,
                    ),
                )
            return ServiceLifecycleResult(
                status="already_running", pid=existing_pid, command=existing_command
            )

        requested_ports = service_ports_from_command(launch_command)
        if not automatic_ports and process_port.ports_in_use(requested_ports):
            return ServiceLifecycleResult(
                status="failed",
                error=ServicePortsActiveError(
                    "Target ports are already occupied by another process"
                ),
            )

        log_path = detail_path_for_home(elfie_home)
        environment = {
            MANAGED_START_ENV: "1",
            "ELFIENEST_SUPERVISED": "1",
            "ELFIENEST_RUNTIME_LOG": str(log_path),
            "ELFIENEST_JOB_NAME": (
                "Local\\ElfieNest.core."
                + hashlib.sha256(str(elfie_home.resolve()).encode("utf-8")).hexdigest()[
                    :24
                ]
            ),
        }
        if child_environment is not None:
            environment.update(child_environment)
        # The selected data root owns diagnostics.  A caller may add child
        # settings, but it cannot redirect the managed service log into a
        # different task's root.
        environment["ELFIENEST_RUNTIME_LOG"] = str(log_path)
        pid = process_port.launch(
            launch_command,
            resolved_root,
            environment=environment,
        )
        if pid <= 0:
            return ServiceLifecycleResult(
                status="failed",
                error=LaunchFailedError(f"Launcher returned invalid PID {pid}"),
            )

        try:
            launched_process = process_port.inspect(pid)
            launch_birth_identity = launched_process.birth_identity
        except (OSError, RuntimeError, ValueError):
            launch_birth_identity = None
        if not launch_birth_identity:
            return cleanup_failed_start(
                pid=pid,
                pid_path=elfie_home / "elfienest.pid",
                original_error=LaunchFailedError(
                    f"Core PID {pid} has no verifiable birth identity"
                ),
                process_port=process_port,
                expected_cwd=resolved_root,
                expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                expected_command=launch_command,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                monotonic=monotonic,
                sleeper=sleeper,
                expected_birth_identity="",
            )

        pid_path = elfie_home / "elfienest.pid"
        try:
            process_port.register_receipt(elfie_home, pid)
        except OSError as error:
            launch_error = LaunchFailedError(f"Unable to register PID {pid}: {error}")
            return cleanup_failed_start(
                pid=pid,
                pid_path=pid_path,
                original_error=launch_error,
                process_port=process_port,
                expected_cwd=resolved_root,
                expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                expected_command=launch_command,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
                monotonic=monotonic,
                sleeper=sleeper,
                expected_birth_identity=launch_birth_identity,
            )

        startup_lease.release()
        lease_released = True
        deadline = monotonic() + timeout_seconds
        while True:
            if not process_port.exists(pid):
                process_port.remove_receipt(elfie_home, pid)
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=LaunchFailedError(
                        "Service exited before passing the health check; "
                        f"inspect service log: {log_path}"
                    ),
                    command=launch_command,
                )
            try:
                healthy = health_checker()
            except (OSError, RuntimeError, ValueError) as error:
                return cleanup_failed_start(
                    pid=pid,
                    pid_path=pid_path,
                    original_error=HealthCheckFailedError(
                        pid,
                        timeout_seconds,
                        detail_path_for_home(elfie_home),
                        str(error),
                    ),
                    process_port=process_port,
                    expected_cwd=resolved_root,
                    expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                    expected_command=launch_command,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    monotonic=monotonic,
                    sleeper=sleeper,
                    expected_birth_identity=launch_birth_identity,
                )
            if healthy:
                return ServiceLifecycleResult(
                    status="started", pid=pid, command=launch_command
                )
            if monotonic() >= deadline:
                return cleanup_failed_start(
                    pid=pid,
                    pid_path=pid_path,
                    original_error=HealthCheckFailedError(
                        pid, timeout_seconds, detail_path_for_home(elfie_home)
                    ),
                    process_port=process_port,
                    expected_cwd=resolved_root,
                    expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                    expected_command=launch_command,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    monotonic=monotonic,
                    sleeper=sleeper,
                    expected_birth_identity=launch_birth_identity,
                )
            sleeper(poll_interval_seconds)
    except (OSError, ValueError) as error:
        return ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(str(error))
        )
    finally:
        if not lease_released:
            startup_lease.release()
