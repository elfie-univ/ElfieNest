"""Foreground CLI session glue for the authoritative Runtime Supervisor."""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from types import FrameType
from typing import Callable, Final, Optional, Sequence

from app.interfaces.cli import lifecycle_commands
from app.orchestration.lifecycle import (
    BackendTier,
    FrontendPreparationError,
    LaunchFailedError,
    LifecycleFacade,
    ServiceLifecycleResult,
)

WaitOnce = Callable[[threading.Event], bool]
HEALTH_CHECK_INTERVAL_SECONDS: Final = 0.5
TERMINAL_HEALTH_STATES: Final = frozenset((BackendTier.OFFLINE,))


def run_foreground_service(
    lifecycle: LifecycleFacade,
    options: Sequence[str],
    *,
    wait_once: Optional[WaitOnce] = None,
    selected_home: Path | None = None,
) -> ServiceLifecycleResult:
    """Run one foreground-owned Runtime generation until shutdown."""
    command = lifecycle.default_service_command(options)
    target_was_explicit = selected_home is not None
    selected_home = lifecycle_commands._data_home_for_command(
        lifecycle,
        command,
        selected_home=selected_home,
    )
    command = lifecycle_commands._select_automatic_ports(
        lifecycle,
        command,
        selected_home,
    )
    before_projection = lifecycle_commands._safe_runtime_projection(
        lifecycle, selected_home
    )
    lifecycle_commands._print_lifecycle_intent(
        "serve",
        selected_home,
        projection=before_projection,
        command=command,
    )
    progress = lifecycle_commands.ProgressIndicator("Starting foreground service")
    progress.start()
    try:
        http_port = lifecycle_commands._validated_http_port(command)
    except ValueError as error:
        progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(
            status="failed",
            command=command,
            error=LaunchFailedError(f"Invalid service port arguments: {error}"),
        )
        lifecycle_commands._print_start_result(
            lifecycle,
            result,
            selected_home=selected_home,
            action="serve",
            compact=True,
        )
        return result

    try:
        lifecycle_commands._prepare_frontend_for_launch(
            lifecycle,
            show_output=True,
        )
    except FrontendPreparationError as error:
        progress.stop(success=False, clear_only=True)
        result = ServiceLifecycleResult(
            status="failed",
            command=command,
            error=LaunchFailedError(f"Frontend build failed: {error}"),
        )
        lifecycle_commands._print_start_result(
            lifecycle,
            result,
            selected_home=selected_home,
            action="serve",
            compact=True,
        )
        return result

    if target_was_explicit:
        supervisor = lifecycle_commands._supervisor_for(
            lifecycle,
            command,
            http_port,
            selected_home=selected_home,
        )
    else:
        supervisor = lifecycle_commands._supervisor_for(
            lifecycle,
            command,
            http_port,
        )
    try:
        started = supervisor.start(owner_id=f"cli-serve:{os.getpid()}")
    finally:
        progress.stop(
            success="started" in locals()
            and started.status in {"started", "already_running"},
            clear_only=True,
        )
    lifecycle_commands._print_start_result(
        lifecycle,
        started,
        selected_home=selected_home,
        action="serve",
        compact=True,
    )
    if started.status != "started":
        return started

    print("  💡 Press Ctrl+C to stop the foreground service.")

    shutdown_requested = threading.Event()
    wait = wait_once or (lambda event: event.wait(HEALTH_CHECK_INTERVAL_SECONDS))

    def request_shutdown(_signum: int, _frame: Optional[FrameType]) -> None:
        shutdown_requested.set()

    previous_sigterm_handler = signal.signal(signal.SIGTERM, request_shutdown)
    try:
        try:
            while True:
                health = supervisor.status()
                if health.tier in TERMINAL_HEALTH_STATES:
                    lifecycle_commands._print_lifecycle_intent(
                        "stop",
                        selected_home,
                        projection=health,
                        command=started.command or command,
                    )
                    stop_progress = lifecycle_commands.ProgressIndicator(
                        "Stopping foreground service"
                    )
                    stop_progress.start()
                    try:
                        supervisor.stop()
                    finally:
                        stop_progress.stop(clear_only=True)
                    failure = ServiceLifecycleResult(
                        status="failed",
                        pid=started.pid,
                        command=started.command or command,
                        error=LaunchFailedError(
                            f"Foreground Runtime health changed to {health.tier.value}"
                        ),
                    )
                    _print_stop_result(
                        lifecycle,
                        selected_home,
                        failure,
                        projection=health,
                    )
                    return failure
                if wait(shutdown_requested):
                    return _stop_foreground_runtime(
                        lifecycle,
                        supervisor,
                        selected_home,
                        command=started.command or command,
                        projection=health,
                    )
        except KeyboardInterrupt:
            _stop_foreground_runtime(
                lifecycle,
                supervisor,
                selected_home,
                command=started.command or command,
            )
            raise
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


def _print_stop_result(
    lifecycle: LifecycleFacade,
    selected_home: Path,
    result: ServiceLifecycleResult,
    *,
    projection=None,
) -> None:
    lifecycle_commands._print_lifecycle_result(
        "stop",
        selected_home,
        result,
        projection=None,
        before_projection=projection,
        command=result.command or (),
    )


def _stop_foreground_runtime(
    lifecycle: LifecycleFacade,
    supervisor,
    selected_home: Path,
    *,
    command: Sequence[str],
    projection=None,
) -> ServiceLifecycleResult:
    """Stop the foreground generation with the same compact identity panel."""
    before_projection = projection or lifecycle_commands._safe_runtime_projection(
        lifecycle, selected_home
    )
    lifecycle_commands._print_lifecycle_intent(
        "stop",
        selected_home,
        projection=before_projection,
        command=command,
    )
    progress = lifecycle_commands.ProgressIndicator("Stopping foreground service")
    progress.start()
    try:
        stopped = supervisor.stop()
    finally:
        progress.stop(
            success="stopped" in locals()
            and stopped.status in {"stopped", "already_stopped"},
            clear_only=True,
        )
    _print_stop_result(
        lifecycle,
        selected_home,
        stopped,
        projection=before_projection,
    )
    return stopped
