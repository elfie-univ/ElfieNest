from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from types import FrameType
from typing import Optional, Union

import pytest

from app.interfaces.cli import foreground_runtime, lifecycle_commands
from app.orchestration.lifecycle.runtime_health import (
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    ServiceLifecycleResult,
)


class FakeSupervisor:
    """Record foreground ownership and lifecycle ordering without real processes."""

    def __init__(
        self,
        start_result: ServiceLifecycleResult,
        *,
        health_states: tuple[RuntimeHealthState, ...] = (),
        stop_result: Optional[ServiceLifecycleResult] = None,
    ) -> None:
        self.start_result = start_result
        self.health_states = list(health_states)
        self.stop_result = stop_result or ServiceLifecycleResult(status="stopped")
        self.calls: list[str] = []
        self.owner_ids: list[str] = []

    def start(self, *, owner_id: str) -> ServiceLifecycleResult:
        self.calls.append("start")
        self.owner_ids.append(owner_id)
        return self.start_result

    def status(self) -> RuntimeHealth:
        self.calls.append("status")
        state = self.health_states.pop(0)
        return RuntimeHealth(
            state=state,
            generation=1,
            owner_lease=None,
            components=(),
        )

    def stop(self) -> ServiceLifecycleResult:
        self.calls.append("stop")
        return self.stop_result


def _wire_supervisor(
    monkeypatch: pytest.MonkeyPatch,
    supervisor: FakeSupervisor,
    command: tuple[str, ...],
) -> tuple[
    list[tuple[str, ...]],
    list[tuple[str, ...]],
    list[tuple[tuple[str, ...], int]],
]:
    built_options: list[tuple[str, ...]] = []
    validated_commands: list[tuple[str, ...]] = []
    factory_calls: list[tuple[tuple[str, ...], int]] = []

    def build(options: tuple[str, ...]) -> tuple[str, ...]:
        built_options.append(options)
        return command

    def build_supervisor(
        selected_command: tuple[str, ...], selected_port: int
    ) -> FakeSupervisor:
        factory_calls.append((selected_command, selected_port))
        return supervisor

    def validate(selected_command: tuple[str, ...]) -> int:
        validated_commands.append(selected_command)
        return 8123

    monkeypatch.setattr(lifecycle_commands, "default_service_command", build)
    monkeypatch.setattr(lifecycle_commands, "_validated_http_port", validate)
    monkeypatch.setattr(lifecycle_commands, "_supervisor_for", build_supervisor)
    monkeypatch.setattr(foreground_runtime.os, "getpid", lambda: 4242)
    return built_options, validated_commands, factory_calls


def test_foreground_start_reuses_command_validation_and_supervisor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    command = ("/tmp/core", "--port", "8123")
    supervisor = FakeSupervisor(ServiceLifecycleResult(status="already_running"))
    built_options, validated_commands, factory_calls = _wire_supervisor(
        monkeypatch, supervisor, command
    )

    # When
    result = foreground_runtime.run_foreground_service(("--port", "8123"))

    # Then
    assert result.status == "already_running"
    assert built_options == [("--port", "8123")]
    assert validated_commands == [command]
    assert factory_calls == [(command, 8123)]
    assert supervisor.owner_ids == ["cli-serve:4242"]


def test_start_failure_returns_without_waiting_or_stopping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    start_error = LaunchFailedError("Core unavailable")
    supervisor = FakeSupervisor(
        ServiceLifecycleResult(status="failed", error=start_error)
    )
    _wire_supervisor(monkeypatch, supervisor, ("/tmp/core",))
    waits: list[bool] = []

    # When
    result = foreground_runtime.run_foreground_service(
        (), wait_once=lambda event: waits.append(event.is_set()) or True
    )

    # Then
    assert result.error is start_error
    assert supervisor.calls == ["start"]
    assert waits == []


def test_already_running_is_not_owned_or_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    supervisor = FakeSupervisor(ServiceLifecycleResult(status="already_running"))
    _wire_supervisor(monkeypatch, supervisor, ("/tmp/core",))

    # When
    result = foreground_runtime.run_foreground_service(
        (), wait_once=lambda _event: pytest.fail("must not wait")
    )

    # Then
    assert result.status == "already_running"
    assert supervisor.calls == ["start"]


def test_keyboard_interrupt_stops_owned_generation_once_then_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    supervisor = FakeSupervisor(
        ServiceLifecycleResult(status="started"),
        health_states=(RuntimeHealthState.READY,),
    )
    _wire_supervisor(monkeypatch, supervisor, ("/tmp/core",))

    def interrupt(_event: threading.Event) -> bool:
        raise KeyboardInterrupt

    # When / Then
    with pytest.raises(KeyboardInterrupt):
        foreground_runtime.run_foreground_service((), wait_once=interrupt)
    assert supervisor.calls == ["start", "status", "stop"]


def test_shutdown_request_stops_once_and_returns_stop_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    stop_result = ServiceLifecycleResult(status="stopped", pid=321)
    supervisor = FakeSupervisor(
        ServiceLifecycleResult(status="started"),
        health_states=(RuntimeHealthState.READY,),
        stop_result=stop_result,
    )
    _wire_supervisor(monkeypatch, supervisor, ("/tmp/core",))
    Handler = Union[Callable[[int, Optional[FrameType]], None], signal.Handlers]
    handlers: list[Handler] = []

    def set_handler(_signal_number: int, handler: Handler) -> Handler:
        handlers.append(handler)
        return signal.Handlers.SIG_DFL

    monkeypatch.setattr(foreground_runtime.signal, "signal", set_handler)

    def request_shutdown(event: threading.Event) -> bool:
        installed_handler = handlers[0]
        assert callable(installed_handler)
        installed_handler(signal.SIGTERM, None)
        return event.is_set()

    # When
    result = foreground_runtime.run_foreground_service((), wait_once=request_shutdown)

    # Then
    assert result is stop_result
    assert supervisor.calls == ["start", "status", "stop"]
    assert len(handlers) == 2
    assert handlers[1] is signal.Handlers.SIG_DFL


@pytest.mark.parametrize(
    "failed_state", (RuntimeHealthState.FAILED, RuntimeHealthState.STOPPED)
)
def test_terminal_health_stops_once_then_returns_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
    failed_state: RuntimeHealthState,
) -> None:
    # Given
    supervisor = FakeSupervisor(
        ServiceLifecycleResult(status="started", pid=123),
        health_states=(failed_state,),
    )
    _wire_supervisor(monkeypatch, supervisor, ("/tmp/core",))

    # When
    result = foreground_runtime.run_foreground_service(
        (), wait_once=lambda _event: pytest.fail("must fail before waiting")
    )

    # Then
    assert result.status == "failed"
    assert isinstance(result.error, LaunchFailedError)
    assert failed_state.value in result.error.detail
    assert supervisor.calls == ["start", "status", "stop"]


def test_ready_and_degraded_health_keep_waiting_until_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    supervisor = FakeSupervisor(
        ServiceLifecycleResult(status="started"),
        health_states=(RuntimeHealthState.READY, RuntimeHealthState.DEGRADED),
    )
    _wire_supervisor(monkeypatch, supervisor, ("/tmp/core",))
    wait_results = iter((False, True))

    # When
    result = foreground_runtime.run_foreground_service(
        (), wait_once=lambda _event: next(wait_results)
    )

    # Then
    assert result.status == "stopped"
    assert supervisor.calls == ["start", "status", "status", "stop"]
