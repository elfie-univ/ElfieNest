"""Foreground CLI session glue for the authoritative Runtime Supervisor."""

from __future__ import annotations

import os
import signal
import threading
from types import FrameType
from typing import Callable, Final, Optional, Sequence

from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle import (
    FrontendPreparationError,
    LaunchFailedError,
    LifecycleFacade,
    RuntimeHealthState,
    ServiceLifecycleResult,
)

WaitOnce = Callable[[threading.Event], bool]
HEALTH_CHECK_INTERVAL_SECONDS: Final = 0.5
TERMINAL_HEALTH_STATES: Final = frozenset(
    (RuntimeHealthState.FAILED, RuntimeHealthState.STOPPED)
)


def run_foreground_service(
    lifecycle: LifecycleFacade,
    options: Sequence[str],
    *,
    wait_once: Optional[WaitOnce] = None,
) -> ServiceLifecycleResult:
    """Run one foreground-owned Runtime generation until shutdown."""
    command = lifecycle_commands.default_service_command(options)
    try:
        http_port = lifecycle_commands._validated_http_port(command)
    except ValueError as error:
        result = ServiceLifecycleResult(
            status="failed",
            command=command,
            error=LaunchFailedError(f"Invalid service port arguments: {error}"),
        )
        lifecycle_commands._print_start_result(lifecycle, result)
        return result

    try:
        lifecycle_commands._prepare_frontend_for_launch(lifecycle)
    except FrontendPreparationError as error:
        result = ServiceLifecycleResult(
            status="failed",
            command=command,
            error=LaunchFailedError(f"Frontend build failed: {error}"),
        )
        lifecycle_commands._print_start_result(lifecycle, result)
        return result

    supervisor = lifecycle_commands._supervisor_for(lifecycle, command, http_port)
    started = supervisor.start(owner_id=f"cli-serve:{os.getpid()}")
    lifecycle_commands._print_start_result(lifecycle, started)
    if started.status != "started":
        return started

    shutdown_requested = threading.Event()
    wait = wait_once or (lambda event: event.wait(HEALTH_CHECK_INTERVAL_SECONDS))

    def request_shutdown(_signum: int, _frame: Optional[FrameType]) -> None:
        shutdown_requested.set()

    previous_sigterm_handler = signal.signal(signal.SIGTERM, request_shutdown)
    try:
        try:
            while True:
                health = supervisor.status()
                if health.state in TERMINAL_HEALTH_STATES:
                    supervisor.stop()
                    failure = ServiceLifecycleResult(
                        status="failed",
                        pid=started.pid,
                        command=started.command or command,
                        error=LaunchFailedError(
                            f"Foreground Runtime health changed to {health.state.value}"
                        ),
                    )
                    print(f"  ❌ Foreground Runtime stopped: {failure.error}")
                    return failure
                if wait(shutdown_requested):
                    stopped = supervisor.stop()
                    _print_stop_result(stopped)
                    return stopped
        except KeyboardInterrupt:
            stopped = supervisor.stop()
            _print_stop_result(stopped)
            raise
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


def _print_stop_result(result: ServiceLifecycleResult) -> None:
    if result.status == "stopped":
        print("  ✅ Foreground Runtime stopped")
        return
    if result.status == "already_stopped":
        print("  ⭕ Foreground Runtime already stopped")
        return
    print(f"  ❌ Failed to stop foreground Runtime: {result.error}")
