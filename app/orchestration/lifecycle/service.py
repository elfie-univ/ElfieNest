"""Safe lifecycle management for the local ElfieNest service."""

import hashlib
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from app.orchestration.lifecycle.commands import (
    DEFAULT_SERVICE_PORTS,
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
from app.orchestration.lifecycle.start_cleanup import cleanup_failed_start
from app.orchestration.lifecycle.types import (
    HealthCheckFailedError,
    InvalidPidFileError,
    LaunchFailedError,
    ProcessIdentityMismatchError,
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
    """Stop the service only when the PID identity exactly matches this project."""
    pid_path = elfie_home / "elfienest.pid"
    observed_ports = _runtime_ports(runtime_record)
    ports_to_check = observed_ports or DEFAULT_SERVICE_PORTS
    if not process_port.receipt_exists(elfie_home):
        if process_port.ports_in_use(ports_to_check):
            return ServiceLifecycleResult(
                status="failed",
                error=ServicePortsActiveError("Missing verifiable PID receipt"),
            )
        return ServiceLifecycleResult(status="already_stopped")

    try:
        pid_result = recorded_pid(elfie_home, process_port)
    except OSError as error:
        return ServiceLifecycleResult(
            status="failed", error=InvalidPidFileError(pid_path, str(error))
        )
    if isinstance(pid_result, InvalidPidFileError):
        return ServiceLifecycleResult(status="failed", error=pid_result)
    if pid_result is None:
        if process_port.ports_in_use(ports_to_check):
            return ServiceLifecycleResult(
                status="failed",
                error=ServicePortsActiveError("Missing verifiable PID receipt"),
            )
        return ServiceLifecycleResult(status="already_stopped")
    pid = pid_result
    try:
        if not process_port.exists(pid):
            if process_port.ports_in_use(ports_to_check):
                return ServiceLifecycleResult(
                    status="failed",
                    pid=pid,
                    error=ServicePortsActiveError("PID is no longer valid"),
                )
            process_port.remove_receipt(elfie_home, pid)
            return ServiceLifecycleResult(status="already_stopped", pid=pid)
        snapshot = process_port.inspect(pid)
        actual_cwd = snapshot.cwd.resolve()
        actual_command = snapshot.command
    except ProcessInspectionError as error:
        return ServiceLifecycleResult(status="failed", pid=pid, error=error)
    except (OSError, RuntimeError, ValueError) as error:
        inspection_error = ProcessInspectionError(pid, str(error))
        return ServiceLifecycleResult(status="failed", pid=pid, error=inspection_error)

    expected_cwd = project_root.resolve()
    expected_script = (expected_cwd / "scripts" / "serve.py").resolve()
    if actual_cwd != expected_cwd or not command_matches_service(
        actual_command,
        actual_cwd,
        expected_script,
        expected_command,
    ):
        mismatch = ProcessIdentityMismatchError(
            pid, expected_cwd, actual_cwd, expected_script, actual_command
        )
        return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)

    try:
        if not process_port.exists(pid):
            process_port.remove_receipt(elfie_home, pid)
            return ServiceLifecycleResult(status="already_stopped", pid=pid)
        confirmed = process_port.inspect(pid)
        confirmed_cwd = confirmed.cwd.resolve()
        confirmed_command = confirmed.command
    except (OSError, RuntimeError, ValueError) as error:
        inspection_error = ProcessInspectionError(pid, str(error))
        return ServiceLifecycleResult(status="failed", pid=pid, error=inspection_error)
    if confirmed_cwd != actual_cwd or confirmed_command != actual_command:
        mismatch = ProcessIdentityMismatchError(
            pid, expected_cwd, confirmed_cwd, expected_script, confirmed_command
        )
        return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)

    try:
        process_port.terminate(pid)
    except OSError as error:
        signal_error = SignalProcessError(pid, str(error))
        return ServiceLifecycleResult(status="failed", pid=pid, error=signal_error)

    deadline = monotonic() + timeout_seconds
    graceful_deadline = min(
        deadline,
        monotonic() + SERVICE_STOP_GRACE_SECONDS,
    )
    while process_port.exists(pid):
        now = monotonic()
        if now >= graceful_deadline:
            if now >= deadline:
                timeout_error = StopTimeoutError(pid, timeout_seconds)
                return ServiceLifecycleResult(
                    status="failed", pid=pid, error=timeout_error
                )
            try:
                if not process_port.exists(pid):
                    break
                force_snapshot = process_port.inspect(pid)
                force_cwd = force_snapshot.cwd.resolve()
                force_command = force_snapshot.command
            except (OSError, RuntimeError, ValueError) as error:
                inspection_error = ProcessInspectionError(pid, str(error))
                return ServiceLifecycleResult(
                    status="failed", pid=pid, error=inspection_error
                )
            if force_cwd != actual_cwd or force_command != actual_command:
                mismatch = ProcessIdentityMismatchError(
                    pid, expected_cwd, force_cwd, expected_script, force_command
                )
                return ServiceLifecycleResult(status="failed", pid=pid, error=mismatch)
            try:
                process_port.terminate(pid, force=True)
            except OSError as error:
                signal_error = SignalProcessError(pid, str(error))
                return ServiceLifecycleResult(
                    status="failed", pid=pid, error=signal_error
                )
            force_deadline = min(
                deadline,
                now + SERVICE_STOP_FORCE_GRACE_SECONDS,
            )
            while process_port.exists(pid):
                if monotonic() >= force_deadline:
                    timeout_error = StopTimeoutError(pid, timeout_seconds)
                    return ServiceLifecycleResult(
                        status="failed", pid=pid, error=timeout_error
                    )
                sleeper(poll_interval_seconds)
            break
        sleeper(poll_interval_seconds)
    try:
        target_ports = observed_ports or service_ports_from_command(actual_command)
    except ValueError as error:
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=ProcessInspectionError(
                pid, f"Invalid service port arguments: {error}"
            ),
        )
    if process_port.ports_in_use(target_ports):
        return ServiceLifecycleResult(
            status="failed",
            pid=pid,
            error=ServicePortsActiveError(
                "Service ports are still occupied after the target process exited"
            ),
        )
    process_port.remove_receipt(elfie_home, pid)
    return ServiceLifecycleResult(
        status="stopped",
        pid=pid,
        command=restart_command_from_process(actual_command),
    )


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
            launch_command,
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
            try:
                existing_healthy = health_checker()
            except (OSError, RuntimeError, ValueError):
                existing_healthy = False
            if not existing_healthy:
                return ServiceLifecycleResult(
                    status="failed",
                    pid=existing_pid,
                    command=existing_command,
                    error=HealthCheckFailedError(existing_pid, 0.0),
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

        environment = {
            MANAGED_START_ENV: "1",
            "ELFIENEST_SUPERVISED": "1",
            "ELFIENEST_JOB_NAME": (
                "Local\\ElfieNest.core."
                + hashlib.sha256(str(elfie_home.resolve()).encode("utf-8")).hexdigest()[
                    :24
                ]
            ),
        }
        if child_environment is not None:
            environment.update(child_environment)
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
                        "Service exited before passing the health check"
                    ),
                    command=launch_command,
                )
            try:
                healthy = health_checker()
            except (OSError, RuntimeError, ValueError):
                return cleanup_failed_start(
                    pid=pid,
                    pid_path=pid_path,
                    original_error=HealthCheckFailedError(pid, timeout_seconds),
                    process_port=process_port,
                    expected_cwd=resolved_root,
                    expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                    expected_command=launch_command,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    monotonic=monotonic,
                    sleeper=sleeper,
                )
            if healthy:
                return ServiceLifecycleResult(
                    status="started", pid=pid, command=launch_command
                )
            if monotonic() >= deadline:
                return cleanup_failed_start(
                    pid=pid,
                    pid_path=pid_path,
                    original_error=HealthCheckFailedError(pid, timeout_seconds),
                    process_port=process_port,
                    expected_cwd=resolved_root,
                    expected_script=(resolved_root / "scripts" / "serve.py").resolve(),
                    expected_command=launch_command,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    monotonic=monotonic,
                    sleeper=sleeper,
                )
            sleeper(poll_interval_seconds)
    except (OSError, ValueError) as error:
        return ServiceLifecycleResult(
            status="failed", error=LaunchFailedError(str(error))
        )
    finally:
        if not lease_released:
            startup_lease.release()
